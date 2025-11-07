"""Simple local generator that simulates AI-created questions."""
from __future__ import annotations

import json
import random
import sqlite3
from datetime import datetime
from pathlib import Path

# Database configuration shared with the Flask app.
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE = BASE_DIR / "cyberquiz.db"


def generate_questions() -> list[dict[str, str | bool]]:
    """Return a list of cybersecurity yes/no statements.

    The function simulates an AI model by picking random templates. In a real-world
    scenario you could replace this with a call to an actual LLM API.
    """

    themes = [
        ("phishing", "Les emails de phishing contiennent toujours des fautes d'orthographe."),
        (
            "mots de passe",
            "Utiliser le même mot de passe sur plusieurs sites augmente les risques de compromission.",
        ),
        ("rgpd", "Le RGPD s'applique uniquement aux entreprises situées en Europe."),
        ("wifi", "Un réseau Wi-Fi protégé par WPA2 est plus sécurisé qu'un réseau WEP."),
        (
            "mises à jour",
            "Les mises à jour logicielles corrigent souvent des failles de sécurité critiques.",
        ),
        ("phishing", "Les banques demandent régulièrement des informations sensibles par email."),
    ]

    random.shuffle(themes)
    questions = []
    for theme, statement in themes[: random.randint(3, 5)]:
        question = {
            "texte": statement,
            # The answer is marked as True when the statement is correct.
            "reponse": statement in {
                "Utiliser le même mot de passe sur plusieurs sites augmente les risques de compromission.",
                "Un réseau Wi-Fi protégé par WPA2 est plus sécurisé qu'un réseau WEP.",
                "Les mises à jour logicielles corrigent souvent des failles de sécurité critiques.",
            },
            "theme": theme,
            "source": "Générateur local",
        }
        questions.append(question)
    return questions


def save_questions(questions: list[dict[str, str | bool]]) -> None:
    """Insert the generated questions in the database with an 'en_attente' status."""

    conn = sqlite3.connect(DATABASE)
    try:
        for item in questions:
            conn.execute(
                """
                INSERT INTO questions (texte, reponse, theme, source, statut)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item["texte"], int(item["reponse"]), item["theme"], item["source"], "en_attente"),
            )
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    """Generate questions and print a JSON summary for transparency."""

    DATABASE.touch(exist_ok=True)
    questions = generate_questions()
    save_questions(questions)
    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "count": len(questions),
        "questions": questions,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
