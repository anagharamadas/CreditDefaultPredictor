# Serving demo — cold start to scored decision

Measured 2026-09-07 on the development machine (M2 Max). P12 turns this into the
recruiter-facing 5-minute path; this page is the operator's version.

## Prerequisites, stated honestly

The 8-second cold start below assumes the image is built and **a model is already
registered**. A genuinely fresh clone cannot score until that is true, and the
chain is: raw data (Kaggle, DVC-pinned) → `python -m credit_default.ingest` →
`python -m credit_default.flows` (training) → `python -m credit_default.registry`
(register + promote to `@champion`). That is minutes of compute, not seconds, and
P12's demo will need a shortcut — a seeded registry or a tiny pre-trained model —
rather than pretending otherwise.

## Cold start

```bash
docker compose down -v          # destroys containers AND the prediction database
docker compose up -d            # mlflow, postgres, api
```

**First successful `/score`: 8 seconds after `up`.** No manual database step:
the API creates the `predictions` table itself at startup, so an empty volume is
a supported state rather than a broken one.

Note what `down -v` does and does not remove: the Postgres volume is destroyed
(prediction history is disposable and rebuilt by the replay), while `.mlflow/` is
a bind mount — the model registry and run history survive, which is the correct
asymmetry. Deleting a champion model should take deliberate action, not a routine
teardown flag.

## Score a loan

```bash
curl -X POST http://127.0.0.1:8000/score \
  -H "Content-Type: application/json" \
  -H "X-Request-ID: demo-001" \
  -d @tests/fixtures/one_application.json
```

```json
{"id":"1000000","p_default":0.32323035262270194,"decision":"decline",
 "threshold":0.16666666666666666,"cost_ratio_assumed":"5:1 (ADR-0003 [ASSUMED])",
 "model_name":"credit-default-granting","model_version":1,
 "scored_at":"2026-09-07T07:08:26.904453Z",
 "prediction_id":"040d7600-aa74-4aee-9b09-c499955350cd"}
```

Every response states the model version it came from, the threshold applied, and
that the cost ratio behind that threshold is an assumption under review (#70).
`prediction_id` is the caller's receipt: the decision is in the store.

## The three checks worth running

```bash
# 1. the decision was recorded, with its vintage separate from its scoring time
docker compose exec postgres psql -U credit -d predictions \
  -c "SELECT loan_id, scored_at, issue_d, model_version, decision FROM predictions;"

# 2. the request is traceable end to end by its id
docker compose logs api | grep demo-001

# 3a. structure layer (pydantic): an incomplete payload never reaches the model
curl -s -X POST http://127.0.0.1:8000/score -H "Content-Type: application/json" \
  -d '{"id":"1","loan_amnt":999999}' | head -c 200

# 3b. contract layer (pandera): a COMPLETE payload with an out-of-range value
python - <<'PY' | curl -s -X POST http://127.0.0.1:8000/score \
     -H "Content-Type: application/json" -d @- | head -c 200
import json; p = json.load(open("tests/fixtures/one_application.json"))
print(json.dumps(p | {"loan_amnt": 999999.0}))
PY
```

Expect: one row whose `scored_at` is today and whose `issue_d` is the loan's own
2015 vintage; JSON log lines sharing `demo-001` across scoring and completion;
then two different 422s that show the two-layer design — 3a reports *missing
required fields* (pydantic, structure), 3b reports
`{"column":"loan_amnt","check":"in_range(500, 50000)"}` (the training contract,
bounds). The API enforces the same contract object training data passes through,
so the two layers cannot drift apart.

## Failure modes, by design

| Situation | Behaviour | Why |
|---|---|---|
| Registry unreachable / no champion | `/ready` 503 with the error; `/score` 503 | Never score with an unknown model |
| Prediction store down | `/score` 503, decision withheld | A credit decision that cannot be recorded is not made |
| Payload violates the contract | 422 listing violated columns | The API enforces the *training* contract, not a copy |
| Unknown category or extra field | 422 at the pydantic layer | Closed vocabularies; `extra="forbid"` |

## Teardown

```bash
docker compose down            # stop, keep the prediction database
docker compose down -v         # also destroy it
```

## Known operational notes

- Image is ~1.8 GB, dominated by the full `mlflow` package pulled for its client.
  The service never runs a tracking server (that is the official image), so
  `mlflow-skinny` would cut this substantially — deferred as a dependency change
  with project-wide blast radius, not a serving-only tweak. Recorded in BACKLOG.
- The API runs as an unprivileged user (uid 10001).
- Host port 5001 for MLflow because macOS AirPlay occupies 5000.
