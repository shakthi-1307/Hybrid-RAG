"""Interactive accept / edit / reject pass over drafted questions.

This step is what makes the benchmark defensible. An unreviewed LLM-generated
set measures the generator, not the retriever.
"""

from __future__ import annotations

from evaluation.schema import GoldQuestion

MENU = "[a]ccept  [e]dit  [r]eject  [q]uit and save"


def _prompt(label: str, current: str) -> str:
    entered = input(f"  {label} [{current}]: ").strip()
    return entered or current


def review_candidates(candidates: list[GoldQuestion]) -> list[GoldQuestion]:
    accepted: list[GoldQuestion] = []

    print(f"\nReviewing {len(candidates)} drafted questions.")
    print("Reject anything that quotes the source, is vague, or could be")
    print("answered from several sections equally well.\n")

    for index, candidate in enumerate(candidates, start=1):
        print(f"--- {index}/{len(candidates)} ---")
        print(f"  Q: {candidate.question}")
        print(f"  Expected section: {candidate.expected_section}")
        print(f"  Document: {candidate.document_title}")
        print(f"  {MENU}")

        choice = input("  > ").strip().lower()
        if choice == "q":
            break
        if choice == "r":
            continue
        if choice == "e":
            accepted.append(
                candidate.model_copy(
                    update={
                        "question": _prompt("question", candidate.question),
                        "expected_section": _prompt(
                            "expected section", candidate.expected_section
                        ),
                        "note": "edited during review",
                    }
                )
            )
            continue
        accepted.append(candidate)

    print(f"\nAccepted {len(accepted)} of {len(candidates)}.")
    return accepted
