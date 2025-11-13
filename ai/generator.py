"""Ollama-based question generator for CyberQuiz."""
from __future__ import annotations

import argparse
import json
import os
import random
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# The retrieval layer enriches the prompts with existing knowledge so that the
# local model can generate fresh statements.
try:  # pragma: no cover - optional dependency, handled gracefully
    from ai import rag
    from ai.rag import RAGNotAvailableError
except Exception:  # pragma: no cover
    rag = None  # type: ignore[assignment]
    RAGNotAvailableError = RuntimeError  # type: ignore[assignment]

# Database configuration shared with the Flask app.
DATABASE = BASE_DIR / "cyberquiz.db"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")


def build_prompt(theme: str | None, hint: str | None) -> str:
    """Construct the RAG-augmented prompt for the LLM."""

    context_block = ""
    if rag is not None:
        try:
            context_block = rag.build_context_block(theme, hint, limit=6)
        except RAGNotAvailableError:
            context_block = ""

    theme_instruction = (
        f"Concentre-toi sur le thème suivant : {theme}." if theme else "Diversifie les thèmes."
    )

    if hint and not theme:
        # When only a free-form hint is provided, expose it explicitly to the model.
        theme_instruction = f"Inspire-toi de ce contexte : {hint}."
    elif hint and theme:
        theme_instruction += f" Utilise ce contexte supplémentaire : {hint}."

    context_section = f"\n{context_block}\n" if context_block else "\n"

    prompt = f"""
Tu es un expert en cybersécurité. Génère entre 3 et 5 affirmations au format Oui/Non
adaptées à un quiz de sensibilisation. Fournis la réponse correcte et un thème court
(phishing, mots de passe, rgpd, wifi, etc.).

{theme_instruction}
{context_section}
RÉPONDS UNIQUEMENT AVEC DU JSON VALIDE DE LA FORME :
{{
  "questions": [
    {{"texte": "...", "reponse": true|false, "theme": "...", "source": "Ollama - llama3"}}
  ]
}}

Assure-toi que les nouvelles affirmations ne reprennent pas exactement celles
listées dans le contexte ci-dessus.

N'ajoute pas de texte explicatif, uniquement le JSON.
"""
    return prompt.strip()


def call_ollama(theme: str | None, hint: str | None) -> list[dict[str, Any]] | None:
    """Request new questions from a local Ollama instance.

    Returns ``None`` when the model is unreachable or when the payload cannot be
    parsed as JSON. In this case the caller is expected to fall back to the local
    question templates so that the admin interface still works.
    """

    prompt = build_prompt(theme, hint)

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
    for theme_label, statement in themes[: random.randint(3, 5)]:
        question = {
            "texte": statement,
            "reponse": statement in {
                "Utiliser le même mot de passe sur plusieurs sites augmente les risques de compromission.",
                "Un réseau Wi-Fi protégé par WPA2 est plus sécurisé qu'un réseau WEP.",
                "Les mises à jour logicielles corrigent souvent des failles de sécurité critiques.",
            },
            "theme": theme_label,
            "source": "Générateur local",
        }
        questions.append(question)
    return apply_theme_hint(questions)


def apply_theme_hint(questions: list[dict[str, str | bool]]) -> list[dict[str, str | bool]]:
    """Apply the requested theme/context to fallback questions if provided."""

    if not _GENERATION_OPTIONS["theme"] and not _GENERATION_OPTIONS["hint"]:
        return questions

    theme = _GENERATION_OPTIONS["theme"] or "général"
    for question in questions:
        question["theme"] = theme
        if _GENERATION_OPTIONS["hint"]:
            question["texte"] = f"({_GENERATION_OPTIONS['hint']}) {question['texte']}"
    return questions


_GENERATION_OPTIONS = {"theme": None, "hint": None}


def generate_questions() -> list[dict[str, str | bool]]:
    """Return a list of cybersecurity yes/no statements.

    The function first tries to call a local Ollama instance using the llama3 model.
    If the call fails it gracefully falls back to a deterministic local generator.
    """

    theme = _GENERATION_OPTIONS["theme"]
    hint = _GENERATION_OPTIONS["hint"]

    if rag is not None:
        try:
            rag.ensure_populated()
        except RAGNotAvailableError:
            pass

    ollama_questions = call_ollama(theme, hint)
    if ollama_questions:
        return ollama_questions  # type: ignore[return-value]

    return generate_local_fallback()


def normalize(text: str) -> str:
    """Return a normalized version of a question for duplicate comparison."""

    return " ".join(text.strip().split()).casefold()


def is_similar(candidate: str, existing: str, threshold: float = 0.9) -> bool:
    """Return True when two strings are similar enough according to difflib."""

    return SequenceMatcher(None, candidate, existing).ratio() >= threshold


def save_questions(questions: list[dict[str, str | bool]]) -> dict[str, int]:
    """Insert the generated questions in the database with an 'en_attente' status."""

    conn = sqlite3.connect(DATABASE)
    skipped = 0
    inserted = 0
    try:
        rows = conn.execute("SELECT texte FROM questions").fetchall()
        known_texts = [row[0] for row in rows]
        normalized_known = [normalize(text) for text in known_texts]

        for item in questions:
            texte = item["texte"]
            normalized_candidate = normalize(texte)

            duplicate_found = False
            for original, normalized in zip(known_texts, normalized_known):
                if normalized_candidate == normalized:
                    print(f"[DUPLICATE] Question déjà existante : {texte}")
                    duplicate_found = True
                    break
                if is_similar(normalized_candidate, normalized):
                    print(
                        "[DUPLICATE] Question similaire ignorée : "
                        f"{texte} (proche de : {original})"
                    )
                    duplicate_found = True
                    break

            if duplicate_found:
                skipped += 1
                continue

            conn.execute(
                """
                INSERT INTO questions (texte, reponse, theme, source, statut)
                VALUES (?, ?, ?, ?, ?)
                """,
                (texte, int(item["reponse"]), item["theme"], item["source"], "en_attente"),
            )
            known_texts.append(texte)
            normalized_known.append(normalized_candidate)
            inserted += 1
        conn.commit()
    finally:
        conn.close()

    return {"inserted": inserted, "skipped": skipped}


def main() -> None:
    """Generate questions and print a JSON summary for transparency."""

    parser = argparse.ArgumentParser(description="CyberQuiz question generator")
    parser.add_argument(
        "--theme",
        help="Thème ou domaine sur lequel concentrer la génération",
        default=None,
    )
    parser.add_argument(
        "--context",
        help="Contexte libre à fournir au modèle (complément du thème)",
        default=None,
    )
    args = parser.parse_args()

    _GENERATION_OPTIONS["theme"] = args.theme.strip() if args.theme else None
    _GENERATION_OPTIONS["hint"] = args.context.strip() if args.context else None

    DATABASE.touch(exist_ok=True)
    questions = generate_questions()
    result = save_questions(questions)
    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "count": len(questions),
        "questions": questions,
        "inserted": result["inserted"],
        "skipped_duplicates": result["skipped"],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
