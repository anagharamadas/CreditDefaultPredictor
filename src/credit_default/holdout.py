"""The frozen holdout: hashed loan-ID manifest + access guard (Charter §3.3, ticket #24).

The holdout (2016-H2 vintages) is frozen at P3 and first opened for the final P6
report. Three mechanisms make that promise checkable rather than aspirational:

1. **Immutability** — `freeze()` refuses to overwrite an existing manifest. Changing
   the holdout means deleting a committed file, which git history shows forever.
2. **Integrity** — the manifest's sha256 is recorded in a metadata file at freeze
   time; `verify()` recomputes the holdout from the split rules and checks both
   hashes. Tampering with the file, the rules, or the data is detected.
3. **Access guard** — `load_holdout_ids()` raises unless called with
   `i_understand_this_is_for_final_p6_evaluation=True`. Nothing physically stops a
   determined peek, but there is no way to do it *accidentally*, and no way to do
   it without writing an acknowledgment into the calling code.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from credit_default.splits import DEFAULT_CONFIG, HOLDOUT, SplitConfig, split_frame

MANIFEST = Path("data/splits/holdout_manifest.txt")
METADATA = Path("data/splits/holdout_manifest.json")


class HoldoutAccessError(RuntimeError):
    """Raised on any holdout access without the explicit P6 acknowledgment."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _holdout_ids(df: pd.DataFrame, config: SplitConfig) -> list[str]:
    ids = split_frame(df, HOLDOUT, config)["id"].astype(str).tolist()
    return sorted(ids, key=int)


def freeze(
    df: pd.DataFrame,
    manifest: Path = MANIFEST,
    metadata: Path = METADATA,
    config: SplitConfig = DEFAULT_CONFIG,
) -> dict:
    """Write the holdout ID manifest + metadata. Refuses to overwrite: frozen means frozen."""
    if manifest.exists() or metadata.exists():
        raise FileExistsError(
            f"{manifest} already exists — the holdout is frozen. If you believe it must "
            "be re-frozen, that is a charter-level decision: delete the files in a "
            "reviewed PR that says why."
        )
    ids = _holdout_ids(df, config)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("\n".join(ids) + "\n")
    meta = {
        "frozen_on": datetime.now(tz=UTC).date().isoformat(),
        "n_loans": len(ids),
        "sha256": _sha256(manifest),
        "split_rule": {
            "term": "36 months",
            "issue_after": f"{config.validation_end:%Y-%m}",
            "issue_through": f"{config.holdout_end:%Y-%m}",
        },
        "opened_for": "final P6 evaluation only (Charter §3.3)",
    }
    metadata.write_text(json.dumps(meta, indent=2) + "\n")
    return meta


def verify(
    df: pd.DataFrame,
    manifest: Path = MANIFEST,
    metadata: Path = METADATA,
    config: SplitConfig = DEFAULT_CONFIG,
) -> dict:
    """Check the freeze end-to-end; raises on any mismatch. Verifying is always allowed."""
    meta = json.loads(metadata.read_text())
    actual_hash = _sha256(manifest)
    if actual_hash != meta["sha256"]:
        raise HoldoutAccessError(
            f"manifest hash {actual_hash[:12]}… != recorded {meta['sha256'][:12]}… — "
            "the manifest file was modified after freezing"
        )
    recomputed = _holdout_ids(df, config)
    on_disk = manifest.read_text().splitlines()
    if recomputed != on_disk:
        raise HoldoutAccessError(
            f"recomputed holdout ({len(recomputed):,} ids) differs from the frozen "
            f"manifest ({len(on_disk):,} ids) — split rules or data changed after freezing"
        )
    return meta


def load_holdout_ids(
    *,
    i_understand_this_is_for_final_p6_evaluation: bool = False,
    manifest: Path = MANIFEST,
) -> list[str]:
    """The guarded read. The keyword-only flag is the acknowledgment — it will appear,
    spelled out, in any code that opens the holdout, and in that code's review diff."""
    if not i_understand_this_is_for_final_p6_evaluation:
        raise HoldoutAccessError(
            "The holdout is frozen until the final P6 evaluation (Charter §3.3). "
            "Pass i_understand_this_is_for_final_p6_evaluation=True only in the P6 "
            "evaluation harness."
        )
    return manifest.read_text().splitlines()
