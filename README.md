# No-Show Shield

Per-booking no-show risk triage for restaurant reservations: score each booking at creation time, explain the risk in plain English, and recommend one action (nothing / SMS re-confirm / refundable deposit for large parties).

Built on `bookings.csv` (2,600 reservations, 4 restaurants, ~4 months). The model is a 4×4 calibrated bucket table — party-size band × lead-time band — small enough to print, honest enough to backtest.

## Requirements

Python 3.10+. **No dependencies** — stdlib only.

## Run it

All commands from the repo root.

```bash
# 1. The honest backtest: train Jan–Mar, test April, vs three baselines
python3 -m src.demo backtest

# 2. Triage worklist: upcoming at-risk bookings with reasons and actions
python3 -m src.demo worklist

# 3. Score a hypothetical booking interactively
python3 -m src.demo score --party 8 --when "2026-05-14 20:00" --now "2026-05-02 11:00"
python3 -m src.demo score --party 2 --when "2026-05-02 21:00" --now "2026-05-02 11:00"

# 4. Tests (35 — data quality, leakage guards, split integrity, model, honest eval, fairness)
python3 -m unittest discover -s tests
```

## Layout

```
bookings.csv               the dataset
src/
  ingest.py                load + validate CSV, data-quality flags
  features.py              party/lead banding behind a structural leakage guard
  model.py                 calibrated bucket table, tiers, reasons, actions
  evaluate.py              time split, baselines, Wilson CIs, calibration, fairness
  demo.py                  worklist | score | backtest
tests/                     test suite, IDs traceable to docs/design/TEST_MATRIX.md
docs/
  CASES.md                 start here — cases and edge cases we handled, in simple words
  design/PRD.md            spec: problem, decisions & rejected alternatives, success criteria
  design/TEST_MATRIX.md    test cases incl. honesty checks (leakage, time split, baselines)
  WRITEUP.md               what was built, what deliberately wasn't, the tradeoff & who pays
  PROMPTS.md               the AI workflow and prompts behind the build
  brief.pdf                original exercise brief
```

## Reading the output

Each scored booking gets a tier and a sentence, e.g.

```
tier:   HIGH  (estimated no-show probability 68%)
reason: party of 8, booked 12 days ahead; similar bookings no-showed 68% of the time
action: Re-confirm + request refundable deposit / card hold (auto-released on re-confirm).
```

Key honesty properties (enforced by tests, not promises): features use only what is known at booking creation; the train/test split is time-based; the model must beat the free one-line rules a manager could apply today; no accuracy headlines; fairness slices show who bears the false-positive cost. Details in `docs/WRITEUP.md`.
