# Test Matrix — No-Show Shield

Every test here is either automated in `tests/` (marked **A**) or a scripted manual check in the demo walkthrough (marked **M**). Tests that would be tautological were deliberately excluded — see the last section for what was cut and why.

Conventions: model trains on bookings with `created_at` ≤ 2026-03-30 ("train"), is evaluated on later bookings ("test" ≈ April). Outcome evaluation uses only `completed` / `no_show` rows; `cancelled` rows are excluded from outcome metrics (they have no show/no-show outcome) but must still be ingestible and scorable.

## 1. Ingest & data quality (DQ)

| ID | Case | Expectation |
|---|---|---|
| DQ-1 **A** | Parse the real `bookings.csv` | 2,600 rows, all required columns, no duplicate `booking_id`, all timestamps parse |
| DQ-2 **A** | `cancelled_at` consistency | Populated on every `cancelled` row and no others |
| DQ-3 **A** | Known anomaly: 5 rows with `cancelled_at` < `created_at` (same-day clock skew) | Ingest does not crash; rows are kept and flagged in a data-quality report, not silently dropped |
| DQ-4 **A** | Unknown `status` value (synthetic row) | Rejected with a clear error naming the row |
| DQ-5 **A** | Negative or zero lead time (synthetic row: `reservation_at` < `created_at`) | Lead clamped to 0 and flagged; never a negative feature value |
| DQ-6 **A** | Invalid `party_size` at scoring time (0, −2, non-integer) | Scoring rejects with a clear message; never returns a tier for garbage |

## 2. Features & leakage guards (FE)

| ID | Case | Expectation |
|---|---|---|
| FE-1 **A** | Feature construction input surface | The feature function receives only `party_size`, `created_at`, `reservation_at` — passing a record containing `status` or `cancelled_at` raises. This is the structural leakage guard: outcome fields cannot reach features even by future edits |
| FE-2 **A** | Leakage canary | Deliberately attempt to register a feature reading `status` → pipeline raises. (Tests the guard itself, not the absence of a bug we already fixed) |
| FE-3 **A** | No PII in model input | `customer_name`, `customer_phone`, `customer_id` are absent from the feature vector; two bookings identical except name/phone/customer/channel get identical scores |
| FE-4 **A** | Lead-time band boundaries | Exactly 24h and exactly 7×24h land in the documented band (boundary is half-open, `[lo, hi)`); 0h lands in the shortest band |
| FE-5 **A** | Party-size band boundaries | 2→3, 4→5, 5→6 transitions land in the documented bands |
| FE-6 **A** | Out-of-range but plausible scoring input (party 15, lead 60d) | Clamped to the top band; scores successfully with a reason noting the band, not the raw historical cell |

## 3. Time-based split (SP)

| ID | Case | Expectation |
|---|---|---|
| SP-1 **A** | Split is strictly temporal on `created_at` | `max(train.created_at)` < `min(test.created_at)`; no booking appears in both sets; train+test+excluded-cancelled counts sum to 2,600 |
| SP-2 **A** | Booking created exactly at the split instant | Goes to exactly one side per the documented rule (`created_at` ≤ boundary → train) |
| SP-3 **A** | Test-window sanity | Test set contains enough outcomes to evaluate (≥50 no-shows expected ≈ 78); if a different CSV yields fewer, evaluation prints a small-sample warning rather than silently reporting fragile numbers |

## 4. Model & scoring (MD)

| ID | Case | Expectation |
|---|---|---|
| MD-1 **A** | Bucket table fitted from train only | Fitting function takes only the train set; probabilities all in [0,1]; every (party-band × lead-band) cell populated |
| MD-2 **A** | Sparse-bucket fallback | A cell with support below the minimum (n < 20) falls back to the documented coarser estimate (band marginal); scoring never divides by zero. Verified with a synthetic tiny training set |
| MD-3 **A** | Fitted table reflects the known gradient | On the real train data: risk(6+, >7d) > risk(6+, <1d) and risk(6+, >7d) > risk(1–2, >7d) > risk(1–2, <1d). Data-driven sanity, not an assertion of magic numbers |
| MD-4 **A** | Tier mapping boundaries | p = 0.099/0.10 and 0.349/0.35 land in the documented tiers (boundaries half-open, `[lo, hi)` upward); LOW <0.10, MEDIUM 0.10–0.35, HIGH >0.35 |
| MD-5 **A** | Reason string content | Contains the party size, the lead time in days, and the historical rate for the booking's bucket — e.g. "party of 8, booked 12 days ahead; similar bookings no-showed 69% of the time" |
| MD-6 **A** | Action mapping | LOW → none; MEDIUM → SMS re-confirm; HIGH + party ≥6 → re-confirm + refundable deposit; **HIGH + party <6 → re-confirm only** (deposits are large-party only per PRD — this branch is easy to get wrong) |
| MD-7 **A** | Determinism | Same input → same score/tier/reason across runs (no hidden randomness) |

## 5. Honest evaluation (EV) — the core

| ID | Case | Expectation |
|---|---|---|
| EV-1 **A** | Evaluation population | Metrics computed on test-window `completed`/`no_show` rows only; the report states the number of positives and the cancelled-row exclusion |
| EV-2 **A** | Beats baseline (a): rule `party ≥ 6 OR lead > 7d` | PR-AUC(model) **strictly >** PR-AUC(rule); at the rule's own flag count, model recall not below rule recall by ≥ one actual no-show (differences under one no-show — 1/positives — are below measurement resolution and count as ties, per PRD criterion 1). If this fails, the failure is reported as a finding (ship the rule table per PRD) — the test asserts the comparison exists and is correctly computed; a separate marked assertion carries the success criterion so an honest negative result is loud, not hidden |
| EV-3 **A** | Beats baseline (b): party-size-alone | Same comparison structure as EV-2 |
| EV-4 **A** | Beats baseline (c): lead-time-alone | Same comparison structure as EV-2 |
| EV-5 **A** | No accuracy headline | Evaluation report contains precision, recall, flag rate, PR-AUC, and Wilson 95% CIs; plain accuracy appears nowhere (a report field test — accuracy at an 18% base rate rewards "always predict show") |
| EV-6 **A** | Wilson CI correctness | CI function checked against hand-computed known values (e.g., 15/60 → [0.157, 0.372]) |
| EV-7 **A** | Calibration table | Per-bucket predicted vs observed April rates reported; observed rate lies inside the bucket's Wilson CI of the prediction for buckets with n ≥ 20 (CI-based check, not a fixed tolerance, because test-window buckets are small) |
| EV-8 **A** | Thresholds never tuned on test | Tier boundaries and any smoothing parameters are fixed before the test set is read: the evaluation entry point takes an already-fitted, already-configured model. Structural test on the API, same spirit as FE-1 |
| EV-9 **A** | Leakage end-to-end canary | Append a synthetic future booking with a known outcome to the CSV; its outcome must not change any train-fitted number (guards against accidental full-dataset statistics) |

## 6. Fairness & cost visibility (FA)

| ID | Case | Expectation |
|---|---|---|
| FA-1 **A** | Fairness slice present | Report includes flag rate and precision by party-size band and by channel |
| FA-2 **A** | Channel neutrality | Permuting the `channel` column leaves every score unchanged (channel is reported on, never scored on) |
| FA-3 **M** | False-positive cost is stated | Demo backtest tile shows, for the HIGH tier, how many flagged bookings actually showed up (the guests who would have been asked for a deposit unnecessarily) |

## 7. Demo (DM)

| ID | Case | Expectation |
|---|---|---|
| DM-1 **M** | Worklist | Upcoming (test-window) bookings sorted by risk desc; each row: tier, reason, action |
| DM-2 **M** | Interactive scoring | Enter party 8 + date 12 days out → HIGH with deposit action; party 2 + tonight → LOW, no action |
| DM-3 **M** | Backtest tile | Shows train/test windows, flag rate, % of no-show **seats** caught, and the three baseline comparisons side by side |

## Deliberately excluded as tautological

- ~~"Bucket table returns the probability stored in the bucket"~~ — tests the dictionary, not the logic.
- ~~"Tier thresholds equal the configured constants"~~ — restates config.
- ~~Asserting dataset-wide magic numbers (e.g., "no-show rate is 18.1%")~~ — freezes an observation into a test; breaks on any data refresh without indicating a bug. The gradient sanity check MD-3 tests *ordering*, which is the actual modeling assumption.
- ~~"Model beats a majority-class / random classifier"~~ — a strawman baseline; the PRD's baselines are the real bar (EV-2..4).
- ~~Round-trip tests of stdlib behavior (CSV parsing of well-formed files, datetime formatting)~~ — tests Python, not us.

## Red-team safeguard traceability

Split integrity (1) → SP-1/2, EV-8 · as-of-creation features (2) → FE-1/2, EV-9 · customer-history leakage (3) → moot, feature excluded by design (FE-3 keeps identity fields out entirely) · cancelled exclusion (4) → EV-1 · three baselines (5) → EV-2/3/4 · CIs and small-sample honesty (6) → EV-5/6, SP-3 · no accuracy headline (7) → EV-5 · PII ban (8) → FE-3 · fairness slice (9) → FA-1/2/3 · soft-action default & deposit gating (10) → MD-6 · synthetic-data disclosure (11) → Phase 5 write-up · lead clamp & anomaly flags (12) → DQ-3/5.
