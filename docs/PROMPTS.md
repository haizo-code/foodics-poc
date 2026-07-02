# The prompts and workflow behind the build

This project was built with Claude Code, but not as one big "build me a thing" prompt. The workflow was designed so that the human stays the decision-maker and the AI has to earn trust at every step. This document shows the actual structure and the key prompts.

## The workflow: five gated phases

The master prompt set up a hard rule — **the AI stops at the end of every phase and waits for explicit approval; approving one phase never pre-approves the next**:

> *"Work in gated phases. STOP at the end of every phase and wait for my explicit approval before starting the next. Five separate gates, not one."*
>
> *"Use parallel sub-agents where it sharpens thinking (competing ideas; red-teaming the approach — for a model, that means data leakage, dishonest evaluation, bias). Read me every sub-agent's output before trusting it."*
>
> *"Keep any model interpretable (I must be able to explain why a booking is flagged). Be honest in evaluation."*

Phases: **1** Explore & ideate (read-only — no code, no files) → **2** PRD → **3** Test matrix → **4** Build → **5** Write-up. Phase 1 additionally ran in the tool's plan mode, which physically blocks file edits.

## Phase 1: competing agents, then independent verification

After a first pass over the data (status rates, no-show by party size / lead time / channel / customer history), three sub-agents ran **in parallel**, each with a different job:

- **Champion A — argue FOR risk scoring.** Prompt excerpt: *"Build the STRONGEST possible case for a 'no-show risk scoring + recommended action' product… Be honest: the main tradeoff, and WHO it costs… Steelman one weakness a skeptic would raise and answer it."*
- **Champion B — argue for anything EXCEPT risk scoring.** Prompt excerpt: *"Champion the best product ideas that are NOT a per-booking predictive no-show risk score… Verify feasibility against the data (e.g., for overbooking: are per-slot volumes big enough? compute bookings per restaurant-day-mealtime)… give a final verdict — be honest, not diplomatic."* This agent killed the overbooking idea with per-slot variance math and conceded nothing it didn't have to.
- **Red team — attack the approach before it exists.** Prompt excerpt: *"Attack the approach on: 1. DATA LEAKAGE — enumerate every concrete leakage trap in this schema… verify with a quick computation how big the leakage risk is… 2. DISHONEST EVALUATION — ways the eval could flatter itself… propose the sensible baseline(s) a fair eval MUST beat… 3. BIAS / FAIRNESS / HARM — who gets systematically flagged… 4. SYNTHETIC-DATA HONESTY… 5. Any data-quality traps."*

Per the master prompt's rule, **no sub-agent claim was trusted unverified**: the "6+ parties = 55% of no-show seats" claim was recomputed from the raw CSV (confirmed: 1,155/2,100), and the red team's "404 bookings carry the history-leakage trap" was reproduced exactly (404 bookings; 459/4,717 prior-pairs).

## Where the AI genuinely helped

- **The red team caught a bug in the AI's own earlier analysis.** The first "leakage-corrected" customer-history computation ordered bookings by reservation date; the red team spotted that a prior booking's *outcome* may still be unknown at the moment a new booking is created, quantified the trap (404 bookings), and showed the honest signal reverses (18.6% vs 20.5%). That catch is why customer history was dropped entirely — and why the code now has a structural feature guard and a fake-future-booking canary test.
- **Falsification with numbers, not vibes.** Overbooking and waitlist ideas were rejected on computed evidence (median 3 bookings/slot, no-show variance > mean; 263 cancellations with 46% giving >24h notice), not intuition.

## Where the AI misled or needed the human gate

- **The naive history signal looked shippable.** A plausible-sounding 19.2%-vs-17.8% "repeat offender" effect was pure leakage. Without an adversarial pass it would likely have shipped as a feature.
- **The success-criterion test failed on first run — and the fix needed human sign-off.** At the rule baseline's own flag count the model trailed by half an expected no-show (out of 78). The AI proposed amending the criterion (PR-AUC must strictly win; recall differences under one actual no-show are ties) but **flagged the amendment at the gate for veto** rather than silently editing the approved PRD. All three artifacts (PRD, test matrix, test docstring) were updated together to tell the same story.
- **A tempting dishonesty was declined.** April results showed the MEDIUM tier flags 65% of bookings. Re-tuning the threshold after seeing test results would have been test-set peeking; it was reported as a finding instead.

## Build discipline

- The **test matrix was written before any code** (Phase 3 before Phase 4), with tautological tests explicitly culled and every test traceable to a matrix ID.
- After the build went green, the suite itself was audited by **mutation testing**: five bugs deliberately introduced one at a time (leakage guard removed, tier boundary moved, deposits-for-everyone, split off-by-one, shrinkage removed) — the suite caught all five.
- Every number quoted in the docs was either computed in-session from the raw CSV or independently re-verified before being written down.
