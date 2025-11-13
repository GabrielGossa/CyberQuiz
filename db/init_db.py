"""Database initialization script for CyberQuiz."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:  # pragma: no cover - optional dependency
    from ai import rag
    from ai.rag import RAGNotAvailableError
except Exception:  # pragma: no cover
    rag = None  # type: ignore[assignment]
    RAGNotAvailableError = RuntimeError  # type: ignore[assignment]

DATABASE = BASE_DIR / "cyberquiz.db"

# Initial set of validated questions to populate the application on first run.
SEED_QUESTIONS = [
    {
        "texte": "Activer l'authentification à deux facteurs renforce la sécurité de vos comptes.",
        "reponse": 1,
        "theme": "authentification",
        "source": "Jeu de base",
        "statut": "valide",
    },
    {
        "texte": "Un antivirus à jour peut détecter toutes les menaces existantes.",
        "reponse": 0,
        "theme": "antivirus",
        "source": "Jeu de base",
        "statut": "valide",
    },
    {
        "texte": "Les liens raccourcis sont toujours sûrs car ils masquent l'adresse complète.",
        "reponse": 0,
        "theme": "phishing",
        "source": "Jeu de base",
        "statut": "valide",
    },
    {
        "texte": "Sauvegarder régulièrement ses données facilite la récupération après une attaque.",
        "reponse": 1,
        "theme": "sauvegarde",
        "source": "Jeu de base",
        "statut": "valide",
    },
]


def create_tables(conn: sqlite3.Connection) -> None:
    """Create the questions and scores tables if they do not exist."""

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            texte TEXT NOT NULL,
            reponse INTEGER NOT NULL,
            theme TEXT,
            source TEXT,
            statut TEXT NOT NULL DEFAULT 'en_attente'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pseudo TEXT NOT NULL UNIQUE,
            score INTEGER NOT NULL,
            mode TEXT NOT NULL,
            date TEXT NOT NULL
        )
        """
    )


def seed_questions(conn: sqlite3.Connection) -> None:
    """Populate the questions table with a basic set of validated questions."""

    existing = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
    if existing:
        return
    conn.executemany(
        """
        INSERT INTO questions (texte, reponse, theme, source, statut)
        VALUES (:texte, :reponse, :theme, :source, :statut)
        """,
        SEED_QUESTIONS,
    )
    conn.commit()


def main() -> None:
    """Entry point that creates the database file and populates it."""

    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE) as conn:
        create_tables(conn)
        seed_questions(conn)
    print(f"Base de données initialisée dans {DATABASE}")

    if rag is not None:
        try:
            count = rag.build_vector_db_from_sqlite()
            print(f"Base vectorielle synchronisée ({count} questions indexées)")
        except RAGNotAvailableError:
            print("Base vectorielle non disponible : installez les dépendances RAG pour l'activer.")


if __name__ == "__main__":
    main()
