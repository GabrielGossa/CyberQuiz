"""Main Flask application for CyberQuiz."""
from __future__ import annotations

import os
import random
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

try:  # pragma: no cover - optional dependency
    from ai import rag
    from ai.rag import RAGNotAvailableError
except Exception:  # pragma: no cover
    rag = None  # type: ignore[assignment]
    RAGNotAvailableError = RuntimeError  # type: ignore[assignment]

# --------------------------------------------------------------------------------------
# Application configuration
# --------------------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "cyberquiz.db"

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("CYBERQUIZ_SECRET", "change-me"),
    ADMIN_USERNAME=os.environ.get("CYBERQUIZ_ADMIN_USER", "admin"),
    ADMIN_PASSWORD=os.environ.get("CYBERQUIZ_ADMIN_PASS", "admin123"),
)


# --------------------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------------------

def get_db() -> sqlite3.Connection:
    """Return a SQLite connection stored in Flask's application context."""

    if "db" not in g:
        # The connection uses row factory to access columns by name.
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db  # type: ignore[return-value]


@app.teardown_appcontext
def close_db(exception: Optional[BaseException]) -> None:
    """Close the database connection at the end of the request."""

    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def fetch_valid_question_ids(theme: Optional[str] = None) -> List[int]:
    """Return a shuffled list of validated question IDs.

    Parameters
    ----------
    theme:
        Optional theme used when the player chooses the "Par thème" mode.
    """

    db = get_db()
    if theme:
        rows = db.execute(
            "SELECT id FROM questions WHERE statut = ? AND theme = ?",
            ("valide", theme),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id FROM questions WHERE statut = ?",
            ("valide",),
        ).fetchall()

    ids = [row["id"] for row in rows]
    random.shuffle(ids)
    return ids


def load_question(question_id: int) -> sqlite3.Row:
    """Retrieve a single question row by its identifier."""

    db = get_db()
    row = db.execute(
        "SELECT * FROM questions WHERE id = ?", (question_id,)
    ).fetchone()
    if row is None:
        abort(404, f"Question {question_id} not found")
    return row


# --------------------------------------------------------------------------------------
# Routes: homepage and quiz flow
# --------------------------------------------------------------------------------------


@app.route("/", methods=["GET", "POST"])
def index():
    """Display the homepage where the user selects their mode."""

    db = get_db()
    themes = db.execute(
        "SELECT DISTINCT theme FROM questions WHERE statut = ? ORDER BY theme",
        ("valide",),
    ).fetchall()

    error: Optional[str] = None
    if request.method == "POST":
        pseudo = request.form.get("pseudo", "").strip()
        mode = request.form.get("mode")
        theme = request.form.get("theme") or None

        # Validate the pseudo to make sure it is present and not already used.
        if not pseudo:
            error = "Le pseudo est obligatoire."
        else:
            existing = db.execute(
                "SELECT 1 FROM scores WHERE pseudo = ? LIMIT 1", (pseudo,)
            ).fetchone()
            if existing:
                error = "Ce pseudo est déjà utilisé. Veuillez en choisir un autre."

        # In theme mode, the player must select a theme from the dropdown list.
        if not error and mode == "theme" and not theme:
            error = "Veuillez choisir un thème pour ce mode."

        if not error:
            # Prepare the session data that stores the progress of the player.
            question_ids = fetch_valid_question_ids(theme if mode == "theme" else None)
            if not question_ids:
                error = "Aucune question disponible pour ce mode actuellement."
            else:
                session.clear()
                session.update(
                    pseudo=pseudo,
                    mode=mode,
                    theme=theme,
                    score=0,
                    index=0,
                    question_ids=question_ids,
                    finished=False,
                )
                return redirect(url_for("quiz"))

        if error:
            flash(error, "danger")

    return render_template("index.html", themes=themes)


@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    """Handle the quiz gameplay flow."""

    if "pseudo" not in session:
        flash("Veuillez démarrer une partie depuis la page d'accueil.", "warning")
        return redirect(url_for("index"))

    question_ids: List[int] = session.get("question_ids", [])
    index = session.get("index", 0)
    score = session.get("score", 0)
    mode = session.get("mode")
    pseudo = session.get("pseudo")

    # When all questions are answered we record the score once and show the summary.
    if index >= len(question_ids):
        if not session.get("finished"):
            db = get_db()
            db.execute(
                "INSERT INTO scores (pseudo, score, mode, date) VALUES (?, ?, ?, ?)",
                (pseudo, score, mode, datetime.utcnow().isoformat()),
            )
            db.commit()
            session["finished"] = True
        return render_template("quiz_finished.html", score=score, total=len(question_ids))

    current_question = load_question(question_ids[index])
    feedback: Optional[Tuple[bool, str]] = None

    if request.method == "POST":
        if request.form.get("timeout") == "true":
            # Time limit reached in chrono mode.
            feedback = (False, "Temps écoulé !")
        else:
            answer = request.form.get("answer")
            if answer not in {"true", "false"}:
                flash("Réponse invalide.", "danger")
                return redirect(url_for("quiz"))

            # Compare the player's answer (true/false) with the stored answer.
            is_correct = (answer == "true") == bool(current_question["reponse"])
            feedback = (
                is_correct,
                "Bonne réponse !" if is_correct else "Mauvaise réponse.",
            )
            if is_correct:
                score += 1
                session["score"] = score

        # Move to the next question after processing.
        session["index"] = index + 1
        return render_template(
            "quiz_result.html",
            question=current_question,
            feedback=feedback,
            remaining=len(question_ids) - (index + 1),
            score=score,
        )

    # GET request: simply show the current question.
    return render_template(
        "quiz.html",
        question=current_question,
        mode=mode,
        remaining=len(question_ids) - index,
    )


# --------------------------------------------------------------------------------------
# Routes: scores and admin interface
# --------------------------------------------------------------------------------------


@app.route("/scores")
def scores():
    """Display the top 10 scores from the scoreboard."""

    db = get_db()
    results = db.execute(
        """
        SELECT pseudo, score, mode, date
        FROM scores
        ORDER BY score DESC, date ASC
        LIMIT 10
        """
    ).fetchall()
    return render_template("scores.html", scores=results)


def require_admin() -> None:
    """Utility decorator-like helper that restricts access to admin pages."""

    if not session.get("is_admin"):
        abort(403)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    """Simple password-protected admin interface."""

    db = get_db()
    is_admin = session.get("is_admin", False)

    # Handle the login form submission first.
    if request.method == "POST" and not is_admin:
        username = request.form.get("username")
        password = request.form.get("password")
        if (
            username == app.config["ADMIN_USERNAME"]
            and password == app.config["ADMIN_PASSWORD"]
        ):
            session["is_admin"] = True
            flash("Connexion réussie.", "success")
            return redirect(url_for("admin"))
        flash("Identifiants invalides.", "danger")

    pending_questions = []
    generation_defaults = session.get(
        "generation_options", {"theme": "", "context": ""}
    )
    if session.get("is_admin"):
        pending_questions = db.execute(
            "SELECT * FROM questions WHERE statut = ? ORDER BY id DESC",
            ("en_attente",),
        ).fetchall()

    return render_template(
        "admin.html",
        is_admin=session.get("is_admin", False),
        pending_questions=pending_questions,
        generation_defaults=generation_defaults,
    )


@app.post("/admin/logout")
def admin_logout():
    """Log the administrator out by clearing the session flag."""

    require_admin()
    session.pop("is_admin", None)
    flash("Déconnexion effectuée.", "info")
    return redirect(url_for("admin"))


@app.post("/admin/questions/<int:question_id>/<action>")
def admin_question_action(question_id: int, action: str):
    """Validate or reject a question currently waiting for approval."""

    require_admin()
    if action not in {"valider", "rejeter"}:
        abort(400)

    new_status = "valide" if action == "valider" else "rejete"
    db = get_db()
    db.execute(
        "UPDATE questions SET statut = ? WHERE id = ?",
        (new_status, question_id),
    )
    db.commit()

    if rag is not None:
        try:
            if new_status == "valide":
                row = db.execute(
                    "SELECT texte, theme, reponse, source FROM questions WHERE id = ?",
                    (question_id,),
                ).fetchone()
                if row:
                    rag.upsert_question(
                        question_id,
                        row["texte"],
                        row["theme"],
                        bool(row["reponse"]),
                        row["source"],
                    )
            else:
                rag.remove_question(question_id)
        except RAGNotAvailableError:
            pass

    flash("Question mise à jour.", "success")
    return redirect(url_for("admin"))


@app.post("/admin/generate")
def admin_generate():
    """Trigger the local AI script that generates new questions."""

    require_admin()
    theme = (request.form.get("generation_theme") or "").strip()
    context_hint = (request.form.get("generation_context") or "").strip()

    session["generation_options"] = {
        "theme": theme,
        "context": context_hint,
    }

    command = [os.environ.get("PYTHON", "python"), "ai/generator.py"]
    if theme:
        command.extend(["--theme", theme])
    if context_hint:
        command.extend(["--context", context_hint])

    try:
        subprocess.run(command, check=True)
        flash("Questions générées. Consultez la liste en attente.", "success")
    except subprocess.CalledProcessError:
        flash("Une erreur est survenue lors de la génération des questions.", "danger")
    return redirect(url_for("admin"))


@app.post("/admin/pending/delete")
def admin_delete_pending():
    """Remove every question that is still waiting for validation."""

    require_admin()
    db = get_db()
    db.execute("DELETE FROM questions WHERE statut = ?", ("en_attente",))
    db.commit()
    flash("La liste des questions en attente a été vidée.", "info")
    return redirect(url_for("admin"))


# --------------------------------------------------------------------------------------
# Application entry point
# --------------------------------------------------------------------------------------


if __name__ == "__main__":
    # Ensure the database exists before starting the server. This avoids confusing
    # errors when running the application for the first time.
    if not DATABASE.exists():
        from db.init_db import main as init_db_main

        init_db_main()
    app.run(debug=True, host="0.0.0.0", port=5000)
