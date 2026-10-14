r"""Block 1: say hello to Gemini through Vertex AI.

Run from the backend folder:
    .\.venv\Scripts\python.exe scripts\hello_gemini.py --list          # which Gemini models can this project use?
    .\.venv\Scripts\python.exe scripts\hello_gemini.py --model NAME    # one tiny call to the model you pick

There is no API key anywhere. The Google library finds the credentials that `gcloud auth application-default login`
saved on this machine, and bills the project named in GOOGLE_CLOUD_PROJECT (backend/.env).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.config  # noqa: F401  (loads backend/.env, which holds GOOGLE_CLOUD_PROJECT)
from app.settings import settings  # noqa: E402
from google import genai  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Say hello to Gemini through Vertex AI.")
    parser.add_argument("--list", action="store_true", help="list the Gemini models this project can use")
    parser.add_argument("--model", default=settings.ai.model or None, help="model name to call")
    args = parser.parse_args()

    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project or project == "your-project-id":
        sys.exit("Set GOOGLE_CLOUD_PROJECT in backend/.env (for example close-the-gap-2026).")

    # vertexai=True means: use Google Cloud (Vertex AI) with our sign-in, not an AI Studio key.
    client = genai.Client(vertexai=True, project=project, location=settings.ai.location)

    if args.list:
        names = sorted(m.name for m in client.models.list(config={"query_base": True}) if "gemini" in (m.name or "").lower())
        print(f"{len(names)} Gemini models visible to project '{project}' (location '{settings.ai.location}'):")
        for n in names:
            print("  ", n)
        return

    if not args.model:
        sys.exit("Pass --model NAME (run with --list to see the names), or set [ai] model in config/settings.toml.")

    response = client.models.generate_content(
        model=args.model,
        contents="Say hello in one short sentence, and name the model you are.",
    )
    print("Model asked:", args.model)
    print("Gemini says:", (response.text or "").strip())
    if response.usage_metadata:
        u = response.usage_metadata
        print(f"Tokens: {u.prompt_token_count} in, {u.candidates_token_count} out")


if __name__ == "__main__":
    main()
