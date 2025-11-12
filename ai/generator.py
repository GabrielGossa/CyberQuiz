"""Ollama-based question generator for CyberQuiz."""
from __future__ import annotations

import json
import os
import random
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

# Database configuration shared with the Flask app.
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE = BASE_DIR / "cyberquiz.db"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")


def call_ollama() -> list[dict[str, Any]] | None:
    """Request new questions from a local Ollama instance.

    Returns ``None`` when the model is unreachable or when the payload cannot be
    parsed as JSON. In this case the caller is expected to fall back to the local
    question templates so that the admin interface still works.
    """

    prompt = """
Tu es un expert en cybersécurité. Génère entre 3 et 5 affirmations au format Oui/Non
adaptées à un quiz de sensibilisation. Fournis la réponse correcte et un thème court
(phishing, mots de passe, rgpd, wifi, etc.).

RÉPONDS UNIQUEMENT AVEC DU JSON VALIDE DE LA FORME :
{
  "questions": [
    {"texte": "...", "reponse": true|false, "theme": "...", "source": "Ollama - llama3"}
  ]
}

N'ajoute pas de texte explicatif, uniquement le JSON.
"""

    request_body = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_URL.rstrip('/')}/api/generate",
        data=request_body,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw_payload = response.read()
    except (urllib.error.URLError, TimeoutError):
        return None

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None

    text = payload.get("response", "")
    if not isinstance(text, str):
        return None

    text = text.strip()
    if text.startswith("```"):
        # Some models wrap JSON in Markdown fences. Remove the first/last lines.
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if text.startswith("json"):
            text = text[4:].lstrip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    items = data.get("questions")
    if not isinstance(items, list):
        return None

    cleaned: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        texte = str(raw.get("texte", "")).strip()
        theme = str(raw.get("theme", "")).strip()
        source = str(raw.get("source", "Ollama - llama3")).strip() or "Ollama - llama3"

        reponse_value = raw.get("reponse")
        if isinstance(reponse_value, str):
            reponse_value = reponse_value.strip().lower() in {"true", "vrai", "oui", "yes"}
        else:
            reponse_value = bool(reponse_value)

        if not texte or not theme:
            continue

        cleaned.append(
            {
                "texte": texte,
                "reponse": bool(reponse_value),
                "theme": theme,
                "source": source,
            }
        )

    if not cleaned:
        return None

    return cleaned


def generate_local_fallback() -> list[dict[str, str | bool]]:
    """Return locally defined questions when Ollama is unavailable."""

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


def generate_questions() -> list[dict[str, str | bool]]:
    """Return a list of cybersecurity yes/no statements.

    The function first tries to call a local Ollama instance using the llama3 model.
    If the call fails it gracefully falls back to a deterministic local generator.
    """

    ollama_questions = call_ollama()
    if ollama_questions:
        return ollama_questions  # type: ignore[return-value]

    return generate_local_fallback()


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
