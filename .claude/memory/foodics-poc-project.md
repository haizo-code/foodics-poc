---
name: foodics-poc-project
description: "Foodics take-home PoC — No-Show Shield (booking risk triage); status, key verified numbers, and honest-eval decisions"
metadata: 
  node_type: memory
  type: project
  originSessionId: 627a6aa5-3059-49ce-b923-6128f3db9552
---

Take-home exercise (submit as git repo/zip, live walkthrough; contact: Sara per docs/brief.pdf). Built July 2, 2026: **No-Show Shield** — per-booking no-show risk triage over bookings.csv (2,600 reservations, 4 restaurants, Jan–Apr 2026). All 5 phases completed and approved.

Key verified facts (recomputed, not assumed): 18.1% no-show rate, 22.7% of booked seats lost; party 6+ & lead >7d → 69% no-show vs 2% small/same-day; parties 6+ = 14.9% of bookings but 55% of no-show seats; customer history has NO leakage-free signal (as-of-creation: 18.6% vs 20.5%, reversed — naive version was leaky); 5 rows have cancelled_at < created_at (clock skew, flagged not dropped).

Implementation: stdlib-only Python (no pandas/pytest on this machine), 4×4 calibrated bucket table (party band × lead band, shrink k=20 toward band-marginal prior), tiers LOW <0.10 / MEDIUM <0.35 / HIGH ≥0.35, deposits large-party-only. Time split at created_at ≤ 2026-03-31. Model PR-AUC 0.384 vs baselines ~0.266. 35 unittest tests traceable to TEST_MATRIX IDs; suite was mutation-tested (5/5 caught).

Notable decision: success criterion amended (user-approved) after first run — matched-flags recall differences under one actual no-show (1/78 positives) count as ties; PR-AUC must strictly beat all baselines. MEDIUM dial flags 65% of bookings — reported honestly, not re-tuned post-test (would be peeking). Related: [[gated-phases-working-style]].
