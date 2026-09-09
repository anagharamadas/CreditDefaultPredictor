"""Replay harness (ticket #55): 2017-2018 loans, month by month, through the LIVE API.

The point of this project's drift story is that nothing is injected. These are real
applications, in their real order, scored by the real service — so the predictions
land in the prediction store having passed the real contract, the real pipeline, and
the real champion model. Computing drift offline in pandas would be faster and would
prove nothing about the system.

**Time is handled honestly.** We do not wait two years. Wall-clock pacing is
compressed to nothing, but the loan's own `issue_d` is preserved and is the axis
every drift measurement uses (which is why the store keeps `issue_d` separate from
`scored_at`). Order is preserved: months are replayed oldest first, so a partial run
is a prefix of a full one rather than a random subset.

**Throughput** (issue #80). Sequentially this is ~6 hours, which would make the
replay unrepeatable and quietly push the work offline into pandas. Client-side
concurrency alone changed NOTHING (33/s at 1 through 24 threads): scoring is
CPU-bound and holds the GIL — pydantic, pandera, pandas, predict — so one server
process serialises everything regardless of how concurrent the caller is. The fix is
server PROCESSES (`UVICORN_WORKERS`), each with its own model copy. Measured on this
machine: 35/s (1 worker) -> 118/s (4) -> 203/s (8), i.e. ~55 minutes for the full
window. `--sample` exists for fast iteration and is a documented loss of precision,
never the default.

Run:  PYTHONPATH=src python -m credit_default.replay --months 2017-01 2017-02
      PYTHONPATH=src python -m credit_default.replay            # the full window
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pandas as pd

from credit_default.features.serving import frame_to_payloads
from credit_default.ingest import INTERIM_ACCEPTED
from credit_default.splits import REPLAY, assign_split, split_frame

API_URL = "http://127.0.0.1:8000"
SOURCE = "replay"
DEFAULT_WORKERS = 32   # measured: 203 loans/s against 8 server processes
TIMEOUT = 30.0


def replay_frame(months: list[str] | None = None) -> pd.DataFrame:
    """Replay-split loans in issue order. Unlabelled loans are INCLUDED: at scoring
    time nobody knows the outcome, and pretending otherwise would rebuild the
    survivorship bias this project exists to avoid."""
    df = assign_split(pd.read_parquet(INTERIM_ACCEPTED))
    frame = split_frame(df, REPLAY)
    frame = frame.assign(month=frame["issue_d"].dt.to_period("M").astype(str))
    if months:
        frame = frame[frame["month"].isin(months)]
    return frame.sort_values(["issue_d", "id"]).reset_index(drop=True)


def already_replayed(months: list[str] | None = None) -> set[str]:
    """Loan ids this replay has already scored — makes a re-run resumable rather
    than a restart, which matters when a full pass takes tens of minutes."""
    from credit_default.store import open_pool

    pool = open_pool()
    try:
        with pool.connection() as conn:
            rows = conn.execute(
                "SELECT loan_id FROM predictions WHERE source = %s", (SOURCE,)
            ).fetchall()
        return {r[0] for r in rows}
    finally:
        pool.close()


def clear_replay_rows(source: str = SOURCE) -> int:
    """Delete rows for one traffic tag. Defaults to the REAL replay, so callers that
    only mean to clean up their own traffic must say which."""
    from credit_default.store import open_pool

    pool = open_pool()
    try:
        with pool.connection() as conn:
            deleted = conn.execute(
                "DELETE FROM predictions WHERE source = %s", (source,)
            ).rowcount
        return int(deleted)
    finally:
        pool.close()


def _score_one(client: httpx.Client, payload: dict, source: str = SOURCE) -> tuple[bool, str]:
    try:
        response = client.post(
            "/score",
            json=payload,
            headers={"X-Source": source, "X-Request-ID": f"replay-{uuid.uuid4()}"},
        )
    except httpx.HTTPError as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if response.status_code == 200:
        return True, ""
    return False, f"HTTP {response.status_code}: {response.text[:120]}"


def replay_month(
    frame: pd.DataFrame,
    workers: int = DEFAULT_WORKERS,
    api_url: str = API_URL,
    source: str = SOURCE,
) -> dict:
    """Score one month's loans concurrently; returns counts and timing.

    `source` tags the rows this call writes. Anything other than a real replay —
    tests above all — must pass its own tag, so that cleaning up after itself cannot
    touch the real replay. (A test that shared this tag once deleted a completed
    665,090-row replay.)
    """
    payloads = frame_to_payloads(frame.drop(columns=["month", "split", "default", "exclusion_reason"]))
    started = time.perf_counter()
    ok = 0
    failures: list[str] = []

    limits = httpx.Limits(max_connections=workers, max_keepalive_connections=workers)
    with (
        httpx.Client(base_url=api_url, timeout=TIMEOUT, limits=limits) as client,
        ThreadPoolExecutor(max_workers=workers) as pool,
    ):
        for succeeded, error in pool.map(lambda p: _score_one(client, p, source), payloads):
            if succeeded:
                ok += 1
            elif len(failures) < 5:  # keep a sample, not 600k strings
                failures.append(error)

    elapsed = time.perf_counter() - started
    return {
        "scored": ok,
        "failed": len(payloads) - ok,
        "seconds": round(elapsed, 1),
        "per_second": round(len(payloads) / elapsed, 1) if elapsed else 0.0,
        "failure_sample": failures,
    }


def run_replay(
    months: list[str] | None = None,
    workers: int = DEFAULT_WORKERS,
    sample: float = 1.0,
    resume: bool = True,
    api_url: str = API_URL,
) -> pd.DataFrame:
    frame = replay_frame(months)
    if sample < 1.0:
        frame = frame.groupby("month", group_keys=False).sample(frac=sample, random_state=0)
        print(f"SAMPLED at {sample:.0%} — reduced precision, stated wherever results are used")
    if resume:
        done = already_replayed()
        if done:
            before = len(frame)
            frame = frame[~frame["id"].astype(str).isin(done)]
            print(f"resuming: {before - len(frame):,} loans already scored, {len(frame):,} left")

    results = []
    for month, group in frame.groupby("month", sort=True):
        stats = replay_month(group, workers=workers, api_url=api_url)
        stats["month"] = month
        stats["loans"] = len(group)
        results.append(stats)
        note = f" FAILURES: {stats['failure_sample'][:1]}" if stats["failed"] else ""
        print(
            f"  {month}  {stats['scored']:>6,}/{len(group):,} scored "
            f"in {stats['seconds']:>6.1f}s ({stats['per_second']:>6.1f}/s){note}"
        )
    return pd.DataFrame(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay loans through the live API.")
    parser.add_argument("--months", nargs="*", help="e.g. 2017-01 2017-02 (default: all)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--sample", type=float, default=1.0, help="fraction per month")
    parser.add_argument("--reset", action="store_true", help="delete prior replay rows first")
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--api-url", default=API_URL)
    args = parser.parse_args(argv)

    if args.reset:
        print(f"cleared {clear_replay_rows():,} prior replay rows")

    started = time.perf_counter()
    summary = run_replay(
        months=args.months,
        workers=args.workers,
        sample=args.sample,
        resume=not args.no_resume,
        api_url=args.api_url,
    )
    if summary.empty:
        print("nothing to replay")
        return 0

    total, failed = int(summary["loans"].sum()), int(summary["failed"].sum())
    elapsed = time.perf_counter() - started
    print(
        f"\nreplayed {total - failed:,}/{total:,} loans across {len(summary)} months "
        f"in {elapsed / 60:.1f} min ({total / elapsed:.0f}/s)"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
