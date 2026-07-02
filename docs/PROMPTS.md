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

- **The red team caught a bug in the AI's own earlier analysis.** The first "leakage-corrected" customer-history computation ordered bookings by reservation date; the red team spotted that a prior booking's *outcome* may still be unknown at the moment a new booking is created, quantified the trap (404 bookings), and showed the honest signal reverses (18.6% vs 20.5%). That catch is why customer history was dropped entirely — and why the code now has a structural feature guard and a fake-future-booking canary test. (Why the naive signal looked convincing in the first place is unpacked in the next section.)
- **Falsification with numbers, not vibes.** Overbooking and waitlist ideas were rejected on computed evidence, not intuition. Overbooking: the airline trick only works when no-shows average out over hundreds of seats — here the median restaurant-slot has just **3 bookings**, and its night-to-night no-show swings are *larger than its own average*, so "accept extra covers" would regularly collide with guests who did show up. Waitlist: only 263 cancellations in 4 months, 46% of them already giving more than 24h notice (rebookable with no product at all) — and a waitlist can never touch no-shows themselves, which give zero notice and leave no moment to offer the seat to anyone else.

## Where the AI misled or needed the human gate

- **The naive history signal looked shippable.** A first analysis said guests with a past no-show are more likely to no-show again (19.2% vs 17.8%) — plausible, matches everyone's intuition about "repeat offenders", and tempting to ship as a feature. It was leakage: some of those "past" no-shows had not actually happened yet at the moment the newer booking was created — the analysis was quietly reading the future. Recomputed using only outcomes truly known at booking time, the effect vanished and slightly reversed (18.6% vs 20.5%), and a dose-response check ("does risk climb with each extra *confirmed* no-show?") came back flat. The apparent signal turned out to be **lead time in disguise**: only far-ahead bookings leave room for another booking to resolve badly in the gap, and lead time was already a feature — so even the leak added nothing new. Without an adversarial pass, this would likely have shipped. (The full plain-words story, with the Sara timeline and the ladder table: `CASES.md`.)
- **The success-criterion test failed on first run — and the fix needed human sign-off.** The PRD required the model to beat a free one-line rule ("party ≥ 6 OR lead > 7d"); compared at that rule's own budget of 109 flags, the model caught 39.5 expected no-shows to the rule's 40.0 — behind by **half of one booking, out of only 78 no-shows in the test window**. At that sample size the honest uncertainty on recall is about ±11 percentage points, so half a booking is far below anything measurable: calling it a loss would be false precision, calling it a win would be a lie. The AI proposed calling differences under one whole no-show a tie (while requiring PR-AUC to *strictly* beat every baseline — which it does, 0.384 vs 0.266) but **flagged the amendment at the gate for veto** rather than silently editing the approved PRD. All three artifacts (PRD, test matrix, test docstring) were updated together to tell the same story.
- **A tempting dishonesty was declined.** April results showed the MEDIUM tier flags 65% of bookings — a number that would look better if the tier threshold were nudged upward. But picking a new threshold *because the test results look nicer there* means fitting the setting to April's particular luck — quietly tuning on the exam you already sat, which invalidates the exam. So the pre-registered default stayed, the report prices the 65% openly in its fairness section, and the threshold is documented as a dial the restaurant operator owns.

## Build discipline

- The **test matrix was written before any code** (Phase 3 before Phase 4), with tautological tests explicitly culled — tests that cannot fail (asserting a config value equals itself, or freezing a dataset statistic into an assertion) prove nothing and manufacture false confidence, so they were deleted and are listed in the matrix with the reason for each. Every remaining test is traceable to a matrix ID.
- After the build went green, the suite itself was audited by **mutation testing** — because a suite that passes only proves something if it *fails when the code is broken*. Five bugs were deliberately introduced one at a time (leakage guard removed, tier boundary moved, deposits-for-everyone, split off-by-one, shrinkage removed); the suite caught all five.
- Every number quoted in the docs was either computed in-session from the raw CSV or independently re-verified before being written down.
