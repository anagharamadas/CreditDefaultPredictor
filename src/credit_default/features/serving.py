"""Serve-side frame construction: JSON payloads -> the exact frame dtypes training saw.

This module is the serving half of the parity guarantee. The P8 API will receive
loan applications as JSON; this converter rebuilds a DataFrame with the SAME dtype
policy the ingest module applies to the raw CSV — categories as pandas category,
floats as float64, dates parsed, None -> NaN. The parity test (#28) holds the
round trip to byte-identical pipeline output.

Anything the API does to a request beyond schema validation happens through this
function — never through an ad-hoc DataFrame(...) call. One converter, tested.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from credit_default.ingest import CATEGORICAL_COLS, DATE_COLS, STRING_COLS

#: columns a scoring payload must carry: every ingest column except the target source.
#: (id stays: the prediction store needs it. issue_d stays: scoring-time month.)
PAYLOAD_EXCLUDED = ("loan_status",)


def frame_to_payloads(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Training-side frame -> JSON-safe dicts (what an API client would send).

    Dates become ISO strings, NaN/NA become None, categoricals become plain strings —
    exactly the degradation a real JSON round trip inflicts.
    """
    out = df.drop(columns=[c for c in PAYLOAD_EXCLUDED if c in df.columns])
    payloads = []
    for _, row in out.iterrows():
        payload: dict[str, Any] = {}
        for col, val in row.items():
            if pd.isna(val):
                payload[col] = None
            elif col in DATE_COLS:
                payload[col] = pd.Timestamp(val).strftime("%Y-%m-%d")
            elif col in CATEGORICAL_COLS or col in STRING_COLS:
                payload[col] = str(val)
            else:
                payload[col] = float(val)
        payloads.append(payload)
    return payloads


def payloads_to_frame(payloads: list[dict[str, Any]]) -> pd.DataFrame:
    """JSON payloads -> a frame with the ingest dtype policy applied.

    The pipeline's transform must see identical dtypes whether the frame came from
    the raw CSV (training) or from API requests (serving).
    """
    df = pd.DataFrame(payloads)
    for col in df.columns:
        if col in DATE_COLS:
            df[col] = pd.to_datetime(df[col], format="%Y-%m-%d", errors="raise")
        elif col in CATEGORICAL_COLS:
            df[col] = df[col].astype("category")
        elif col in STRING_COLS:
            df[col] = df[col].astype("string")
        else:
            df[col] = df[col].astype("float64")
    return df
