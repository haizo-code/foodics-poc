# Cases and edge cases we handled — in simple words

A walkthrough of what the system does, one real case at a time. Every runnable case below can be shown live with the command under it. (Numbers come from the model trained on Jan–Mar; your output will match.)

## Everyday cases

**A couple books a table for tonight.**
History says bookings like this almost always show up (~4%). So we do nothing — no text, no deposit, no friction. Most bookings look like this, and leaving them alone is the point: friction is only spent where the risk is.

```bash
python3 -m src.demo score --party 2 --when "2026-05-02 21:00" --now "2026-05-02 11:00"
# LOW — no action
```

**A family of 4 books for next Friday (5 days ahead).**
Riskier (~18% never show), but most still come. So the action is the cheapest one possible: an automatic SMS a day before — "still coming? tap here to cancel." If their plans changed, the table is freed early enough to give to someone else. A silent no-show becomes a useful cancellation.

```bash
python3 -m src.demo score --party 4 --when "2026-05-07 20:00" --now "2026-05-02 11:00"
# MEDIUM — SMS re-confirm
```

**A group of 8 books two weeks ahead.**
This is the booking that hurts: in the data, about 2 out of 3 bookings like this never arrive, and each one wastes 8 seats for the evening. Here — and only here — we ask for a refundable deposit. If they re-confirm, it's released automatically. A real guest loses nothing; a flaky booking now has a reason to cancel early.

```bash
python3 -m src.demo score --party 8 --when "2026-05-14 20:00" --now "2026-05-02 11:00"
# HIGH — re-confirm + refundable deposit
```

## Edge cases we handled on purpose

**A party of 4 booked 12 days ahead — high risk, but NO deposit.**
The risk is high (~40%), so it's flagged and re-confirmed. But deposits are reserved for large parties only, where the damage justifies the friction. A rule that charged every risky booking would punish small groups too much for too little.

```bash
python3 -m src.demo score --party 4 --when "2026-05-14 20:00" --now "2026-05-02 11:00"
# HIGH — re-confirm, no deposit
```

**A party of 15 — bigger than anything in the data.**
The model has never seen 15, but it doesn't crash or guess wildly: it treats it as "a large party" (the 6+ group) and scores it like the biggest bookings it knows.

**A guest who no-showed twice before books again.**
Nothing changes — we deliberately do not use anyone's history. Not because it would be cheating: counting only no-shows that had **already happened and were confirmed** before the new booking was made is perfectly fair. We built exactly that, and ran the "ladder test": if repeat offenders are real, risk should climb with every extra confirmed offense. It doesn't:

| Confirmed past no-shows | How often the NEXT booking is a no-show |
|---|---|
| 0 | 20.5% |
| 1 | 20.2% |
| 2 | 12.8% — *less*, not more |
| 3+ | 20.0% (only 10 cases) |

Flat — no ladder. In this data there are risky *bookings* (big group, booked far ahead), not risky *people*: a guest's old no-show happened because that old booking was risky, and the new booking's risk is already measured directly. Forcing history into the model anyway would teach it something silly — that two past no-shows make a guest *safer*. Two honest footnotes: real-world data might show a real ladder (we'd rerun this exact test before deciding), and a true serial offender — ten in a row, which doesn't exist here; the worst guest has four — is an abuse problem for a human policy, not a model feature. (The separate trap of *accidentally counting no-shows that hadn't happened yet* is covered in the honesty section below.)

**A rare combination the model has barely seen.**
If some party-size × timing combination had too little history (fewer than 20 bookings), the model wouldn't trust its own tiny sample — it leans on broader averages instead, and the explanation says "limited history for this combination." On this dataset every combination happens to have enough data, so the safeguard never fires here — but it's built and tested, because real data won't always be this generous.

**A cancelled booking.**
It never counts against the model's grade. A cancellation isn't a no-show — the guest told us, the table was freed. We only grade on bookings where "showed up or not" actually happened.

**Five weird rows in the data (cancelled *before* they were created).**
Almost certainly clock skew between systems. We keep them, flag them in a data-quality note, and move on — silently deleting odd rows is how real problems get hidden.

## How we kept the grading honest (the part reviewers should poke at)

**The time-travel trap (data leakage) — and how it almost got us twice.**
Follow one guest, Sara:

- **March 1:** Sara books a dinner for **March 20**.
- **March 15:** Sara books a second dinner for **March 22**.
- **March 20:** she no-shows the first booking.

Question: when scoring the *second* booking, may the model know about that no-show? The naive analysis said yes — the first dinner (March 20) comes before the second dinner (March 22), so it looks like "the past." But the second booking was created on **March 15**, five days *before* the no-show happened. On March 15, nobody knew. Using it means predicting Monday with information from Wednesday.

The first "fix" made exactly this mistake in a subtler form: it ordered bookings by dinner date instead of asking "what was already *resolved* when this booking was created?" An adversarial review pass (a second AI agent instructed to attack the analysis) caught it, and quantified it: **404 bookings** in this dataset carry that trap. Computed correctly, the history signal didn't just shrink — it disappeared and slightly reversed. That's why customer history was dropped entirely, and why the code now physically blocks everything except party size and timing from reaching the model. A test even plants a fake future booking in the file and checks that nothing about the trained model changes.

**Studying with old exams, graded on a new one.**
The model learns from January–March and is graded only on April — bookings it has never seen, from a period after everything it learned. Grading it on the same period it studied would flatter it.

**It had to beat the free alternative.**
A manager could apply a one-line rule today for free: "flag big parties and far-ahead bookings." If our model can't beat that, it doesn't deserve to exist. It does beat it overall — and at the one spot where they tied (a difference of half a no-show out of 78), we wrote "tie," not "win."

**We didn't touch the dials after seeing the exam.**
The April results showed the MEDIUM tier texts more guests than we'd like (65% of bookings). Tempting to nudge the threshold and rerun — but tuning after seeing the test results is quietly cheating on the exam you already took. The dials stay where they were set beforehand; the observation is reported instead, as a knob the restaurant owns.

**Small numbers, said out loud.**
April has only 78 no-shows, so every percentage comes with an honest uncertainty range, and the report warns when a number rests on too few cases to trust.
