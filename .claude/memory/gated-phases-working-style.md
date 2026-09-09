---
name: gated-phases-working-style
description: "User's preferred workflow for data/ML PoC projects — hard-gated phases, sub-agent red-teaming, honest evaluation as a first-class requirement"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 627a6aa5-3059-49ce-b923-6128f3db9552
---

For the foodics-data-poc take-home (and likely future data/model work), the user ran a strictly gated 5-phase flow: Explore/Ideate → PRD → Test matrix → Build → Write-up, with an explicit STOP for approval at every gate — approving one phase never pre-approves the next. They wanted parallel sub-agents for competing idea champions plus a dedicated red-team (data leakage, dishonest evaluation, bias), and every sub-agent's full output shown to them before being trusted.

**Why:** they care about honest evaluation more than polished results — the red-team catching leakage in my own analysis (naive customer-history signal) was the most valued moment; they also asked for inline "why" rationale on every design decision in docs, with each rationale living in exactly one place (no duplication).

**How to apply:** on similar projects, propose gated phases with explicit stops; spawn champion + red-team sub-agents during ideation; treat evaluation-criterion changes as user-vetoable and flag them at gates; write decision rationale inline in specs; verify sub-agent claims independently before building on them. Related: [[foodics-poc-project]].
