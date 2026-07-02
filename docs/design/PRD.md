# PRD — No-Show Shield

Per-booking no-show risk triage with recommended actions, for restaurant operators.

## Problem

Across 4 restaurants over ~4 months (2,600 bookings), **18.1% of bookings end as no-shows**. Because no-show parties skew large (avg 4.47 covers vs 3.56 overall), that is **22.7% of all booked seats — 2,100 covers — lost with zero notice**, so the seats cannot be resold. Unlike cancellations (10.1%, and 46% of those give more than 24h notice), no-shows give the restaurant nothing to react to.

The loss is concentrated and predictable at the moment of booking:

| Signal (known at creation time) | No-show rate |
|---|---|
| Party 1–4 | ~13% |
| Party 6+ | 42% |
| Booked <24h ahead | ~5% |
| Booked >7 days ahead | 41% |
| **Party 6+ AND booked >7d ahead** | **69%** (n=97) |
| Party 1–2 AND booked <1d ahead | 2% |

Parties of 6+ are 14.9% of bookings but **55% of all no-show seats**. Today no one acts on this: every booking is treated the same.

## Who it's for

- **Primary: the restaurant manager / host stand.** Sees a daily worklist of upcoming high-risk bookings and takes the suggested action. No data skills assumed — every flag must read as a sentence they could say aloud to a guest.
- **Secondary: the reservations product** (Foodics-style platform) that would embed the score at booking creation to trigger automated confirmations.

## What it does

1. **Scores every booking at creation time** — the only moment the restaurant can attach a condition (deposit, confirmation) without an awkward follow-up call, and the moment both predictive fields are fully known. Features: **party size and booking lead time, nothing else** (what was rejected and why: see *Design decisions* below). The model is a small calibrated bucket table — party-size band × lead-time band → historical no-show probability, fitted on training data — with logistic regression as an alternative only if it demonstrably beats the table.
2. **Assigns a risk tier and explains it in plain English.**
   - Example: `HIGH — party of 8, booked 12 days ahead; similar bookings no-showed 69% of the time.`
3. **Recommends one action per tier** (operator can always override). The principle: friction proportional to risk, because every intervention has a false-positive cost paid by a real guest.
   - **LOW** (<10%): nothing. Most bookings live here (small parties, short lead — as low as 2% no-show); any friction on them is pure downside.
   - **MEDIUM** (10–35%): automated SMS/WhatsApp re-confirmation with one-tap cancel, ~24h before the slot. SMS rather than a deposit because the majority at this level still show up, so the action must be near-costless to the guest; the ~24h timing converts a silent no-show into a cancellation early enough to resell the table.
   - **HIGH** (>35%): re-confirmation plus a refundable deposit / card hold, large parties only, auto-released on re-confirm. Deposits are reserved for this tier because it is the only segment where the odds justify real friction — at the extreme, roughly 2 of 3 bookings no-show and each miss burns 6+ seats.
   - Tier boundaries are set on training data only (keeping the evaluation honest) and are configurable dials — restaurants differ in how much friction they can afford to impose on guests.
4. **Demo surfaces (local only):**
   - Triage worklist: upcoming bookings sorted by risk, with reasons and actions.
   - Interactive scoring: enter party size + reservation date → tier/reason/action.
   - Honest backtest tile: trained on Jan–Mar, replayed on April — flag rate, share of no-show seats caught, versus the baselines in *Success criteria*.

## Design decisions — what we considered and rejected

- **Customer booking history (the obvious feature we deliberately left out).** We have each customer's full history — IDs, prior bookings, when they no-showed — and a naive analysis even shows a small signal (19.2% vs 17.8% next-booking no-show rate). That signal is **data leakage**: it counts prior bookings whose outcome wasn't yet known when the new booking was created (404 bookings in this dataset reference such a prior). Computed honestly — using only bookings *resolved before* the new booking's creation — the effect disappears and slightly reverses: past no-showers no-show **less** (18.6% vs 20.5%). Two further reasons even if a weak signal existed: a third of customers (310 of 917) have only one booking, so the feature is undefined exactly where a new-customer product needs it most; and punishing guests indefinitely for one stale no-show is a reputation system, with all its fairness problems, smuggled in as a feature.
- **Channel, restaurant, day-of-week, hour.** All measured; all weak (e.g., no-show by channel spans only 14.8–20.1%). Adding them buys almost no lift and costs the one-screen interpretability the product depends on.
- **Customer name / phone.** Never enter the model. They can proxy for nationality or customer segment — a discrimination risk with zero predictive payoff to justify it.
- **A fancier model (gradient boosting, neural nets).** Two signals already carry a 35× risk spread, there are only ~2,000 training rows, and the operator must be able to read why a booking was flagged. A table whose every cell is a sentence beats a model that needs explaining.
- **`cancelled_at` / `status`-derived features.** Known only after the outcome — using them (even their presence/absence) is leakage by construction.

## Success criteria

The PoC succeeds only if **all** of these hold on the held-out April window (time split on `created_at` — a random split would let the model train on bookings from the same period it is tested on, flattering the results; a time split mimics real deployment: learn from the past, score the future. Thresholds chosen on training data only, for the same reason):

1. **Beats all three sensible baselines** on precision/recall trade-off: (a) rule `party ≥ 6 OR lead > 7d`, (b) party-size-alone, (c) lead-time-alone. Any manager could implement these one-line rules today for free — if the model can't beat them, the model is unjustified complexity. Concretely: PR-AUC strictly greater than every baseline, and recall at the rule's matched flag count not *losing* to any baseline — where a difference smaller than one actual no-show in the test window is a tie, not a loss (with ~78 test positives, finer differences are below measurement resolution; pretending otherwise would be false precision). If the model genuinely loses, we report that honestly and ship the calibrated rule table as the product.
2. **Calibrated:** predicted probabilities track observed April no-show rates per bucket (calibration table reported). The product recommends charging deposits on the strength of these numbers — if they are inflated, the restaurant imposes friction on guests who didn't warrant it.
3. **Honest reporting:** no accuracy headlines (18% base rate makes "always predict show" 82% accurate); precision/recall reported with Wilson 95% CIs — the April test window has only ~78 no-shows, and we say so.
4. **No leakage:** every feature is computable from data available at `created_at`; cancelled bookings are excluded from outcome evaluation because they have no show/no-show outcome.
5. **Interpretable end-to-end:** every flagged booking carries a reason a manager can read; the entire model fits on one screen.
6. **Fairness slice reported:** flag rate and precision by party-size band and by channel, so the cost of false positives is visible, not hidden.

## Explicit non-goals

- **No overbooking planner.** Median 3 bookings per restaurant-slot and per-slot no-show variance exceeding the mean — at this volume overbooking would routinely deny walk-ins.
- **No waitlist / cancellation-recovery product.** Only 263 cancellations in 4 months across 4 restaurants, and 46% already give >24h notice (rebookable without any product). Crucially, a waitlist can never touch the no-show problem itself: no-shows give zero notice, so there is no moment to offer the seat to someone else. Recovery attacks the small leak; prevention attacks the big one.
- **No customer-level reputation or blacklist.** No honest signal supports one (see *Design decisions*).
- **No actual SMS/payment integration.** Actions are recommendations printed by the PoC; wiring up Twilio/payment holds is production work, not proof of the idea.
- **No deployment, auth, or multi-tenant anything.** Runs locally on the CSV.
- **No real-world performance claims.** The data is synthetic; effect sizes are planted. The PoC proves the mechanism and the honest-evaluation harness, not production lift.

## Main tradeoff — and who pays it

**Targeted friction in exchange for recovered seats.** At the HIGH tier, roughly **3 in 10 flagged guests would have shown up anyway** and get asked for a deposit; at MEDIUM, well-intentioned guests get confirmation nags. The cost lands on a specific group: **large-party, plan-ahead guests — often a restaurant's most valuable bookings** — and disproportionately on whoever books furthest ahead. There is also a feedback-loop risk: deposits deter exactly the bookings the model flags, which suppresses legitimate large-party demand and can make the model look self-confirming.

Mitigations built into the design: soft actions (SMS) as the default, deposits only at the extreme tail (~top 4% of bookings, where historical no-show is ~69%), refundable and auto-released holds, and operator override on every recommendation. The alternative — blanket deposits or doing nothing — either taxes the 2%-risk same-day couple or keeps burning 22.7% of seats; targeted friction is the least-bad allocation of the pain.
