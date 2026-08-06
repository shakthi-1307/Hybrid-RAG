"""Benchmark CLI.

    python -m evaluation generate --email you@example.com
    python -m evaluation review
    python -m evaluation run --email you@example.com

Run inside the API container so it shares the database, vector store, and
models:

    docker compose exec api python -m evaluation run --email you@example.com
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import SessionFactory
from app.logging_config import configure_logging
from app.stores import user_repository
from evaluation.generate import draft_questions
from evaluation.goldset import (
    load_candidates,
    load_goldset,
    save_candidates,
    save_goldset,
)
from evaluation.generation_runner import run_generation_evaluation
from evaluation.report import (
    render_generation_markdown,
    render_markdown,
    write_generation_json,
    write_generation_markdown,
    write_json,
    write_markdown,
)
from evaluation.review import review_candidates
from evaluation.runner import run_evaluation
from evaluation.schema import GoldSet

logger = logging.getLogger(__name__)


def _resolve_user(session: Session, email: str) -> User:
    user = user_repository.find_by_email(session, email)
    if user is None:
        raise SystemExit(f"No account found for {email}.")
    return user


def _generate(email: str) -> None:
    with SessionFactory() as session:
        user = _resolve_user(session, email)
        questions = draft_questions(session, user.id)

    path = save_candidates(
        GoldSet(version=1, owner_email=email, questions=questions)
    )
    print(f"\nDrafted {len(questions)} candidates -> {path}")
    print("Review them before running the benchmark:")
    print("  python -m evaluation review")


def _review() -> None:
    candidates = load_candidates()
    accepted = review_candidates(candidates.questions)
    if not accepted:
        raise SystemExit("Nothing accepted; gold set not written.")

    path = save_goldset(candidates.owner_email, accepted)
    print(f"Gold set written to {path}")


def _run(email: str) -> None:
    goldset = load_goldset()
    with SessionFactory() as session:
        user = _resolve_user(session, email)
        report = run_evaluation(session, goldset, user.id)

    json_path = write_json(report)
    markdown_path = write_markdown(report)

    print()
    print(render_markdown(report))
    print(f"\nJSON:     {json_path}")
    print(f"Markdown: {markdown_path}")


def _generation(email: str) -> None:
    goldset = load_goldset()
    with SessionFactory() as session:
        user = _resolve_user(session, email)
        report = run_generation_evaluation(session, goldset, user.id)

    json_path = write_generation_json(report)
    markdown_path = write_generation_markdown(report)

    print()
    print(render_generation_markdown(report))
    print(f"\nJSON:     {json_path}")
    print(f"Markdown: {markdown_path}")


def main(argv: list[str] | None = None) -> None:
    configure_logging()

    parser = argparse.ArgumentParser(prog="evaluation")
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="draft candidate questions")
    generate.add_argument("--email", required=True)

    commands.add_parser("review", help="accept/edit/reject drafted questions")

    run = commands.add_parser("run", help="benchmark retrieval configurations")
    run.add_argument("--email", required=True)

    generation = commands.add_parser(
        "generation", help="benchmark answer quality (RAGAS + citation integrity)"
    )
    generation.add_argument("--email", required=True)

    arguments = parser.parse_args(argv)
    if arguments.command == "generate":
        _generate(arguments.email)
    elif arguments.command == "review":
        _review()
    elif arguments.command == "run":
        _run(arguments.email)
    else:
        _generation(arguments.email)


if __name__ == "__main__":
    main(sys.argv[1:])
