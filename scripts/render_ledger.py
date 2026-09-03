"""Render docs/LEAKAGE_LEDGER.md from src/credit_default/ledger.py.

The Python dict is the authority; this document is its readable projection.
Run:  PYTHONPATH=src python scripts/render_ledger.py
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from credit_default.ledger import CATEGORIES, LEDGER, UNDECIDED

OUT = Path("docs/LEAKAGE_LEDGER.md")

TITLES = {
    "FEATURE": "FEATURE — eligible for the model matrix",
    "BANNED_POST": "BANNED_POST — populated after origination (leakage)",
    "BANNED_UNDERWRITING": "BANNED_UNDERWRITING — LC's own credit-assessment outputs (Charter §1)",
    "TARGET": "TARGET — outcome source",
    "METADATA": "METADATA — identifiers / process / split keys",
    "EXCLUDED_SCOPE": "EXCLUDED_SCOPE — app-time legitimate, out of v1 by recorded decision",
    "UNDECIDED": "UNDECIDED — must be zero at P2 exit",
}


def main() -> None:
    counts = Counter(cat for cat, _ in LEDGER.values())
    lines = [
        "# Leakage Ledger — all 151 raw columns, classified",
        "",
        "GENERATED from `src/credit_default/ledger.py` by `scripts/render_ledger.py` — the",
        "code is the authority (the P4 feature allowlist imports it); edit there, rerun here.",
        "",
        "Classification question for every column: *could a loan officer have seen this",
        "value at the second the application was submitted — and is it the borrower's",
        "information rather than LendingClub's own assessment of them?*",
        "",
        "| Category | Count |",
        "|---|---|",
    ]
    lines += [f"| {cat} | {counts.get(cat, 0)} |" for cat in CATEGORIES]
    total = sum(counts.values())
    lines += [f"| **total** | **{total}** |", ""]

    if counts.get(UNDECIDED):
        lines += [
            (
                f"> **{counts[UNDECIDED]} columns UNDECIDED** (first-pass state, ticket #18). "
                "Ticket #21 must resolve every one; P2 cannot exit otherwise."
            ),
            "",
        ]

    for cat in CATEGORIES:
        cols = [(c, j) for c, (k, j) in LEDGER.items() if k == cat]
        if not cols:
            continue
        lines += [f"## {TITLES[cat]} ({len(cols)})", "", "| column | justification |", "|---|---|"]
        lines += [f"| `{c}` | {j} |" for c, j in cols]
        lines += [""]

    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT}: {dict(counts)}")


if __name__ == "__main__":
    main()
