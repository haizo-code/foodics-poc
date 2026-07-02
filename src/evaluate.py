"""Honest evaluation: time split, three real baselines, Wilson CIs, calibration,
fairness slices. No accuracy headlines anywhere — at an 18% base rate,
'always predict show' scores 82% and means nothing.
"""
import datetime as dt
from math import sqrt

from .features import PARTY_BANDS, LEAD_BANDS, booking_features

# Bookings created at or before this instant are training data; later ones are test.
SPLIT_AT = dt.datetime(2026, 3, 31, 0, 0)
MIN_TEST_POSITIVES = 50


def time_split(bookings, boundary=SPLIT_AT):
    train = [b for b in bookings if b.created_at <= boundary]
    test = [b for b in bookings if b.created_at > boundary]
    return train, test


def wilson_ci(k, n, z=1.959963985):
    """95% Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def average_precision(scores_and_labels):
    """AP over score-threshold blocks — ties are handled as a block, so a
    binary baseline isn't helped or hurt by row order."""
    total_pos = sum(y for _, y in scores_and_labels)
    if total_pos == 0:
        raise ValueError("no positives to evaluate")
    by_score = {}
    for s, y in scores_and_labels:
        n, pos = by_score.get(s, (0, 0))
        by_score[s] = (n + 1, pos + y)
    ap, tp, fp, prev_recall = 0.0, 0, 0, 0.0
    for s in sorted(by_score, reverse=True):
        n, pos = by_score[s]
        tp += pos
        fp += n - pos
        recall = tp / total_pos
        precision = tp / (tp + fp)
        ap += (recall - prev_recall) * precision
        prev_recall = recall
    return ap


def recall_and_precision_at_flag_count(scores_and_labels, m):
    """Flag the m highest-scored rows (ties broken by score blocks; a partial
    block contributes proportionally). Returns (recall, precision, exact_flagged)."""
    total_pos = sum(y for _, y in scores_and_labels)
    by_score = {}
    for s, y in scores_and_labels:
        n, pos = by_score.get(s, (0, 0))
        by_score[s] = (n + 1, pos + y)
    flagged, tp = 0, 0.0
    for s in sorted(by_score, reverse=True):
        n, pos = by_score[s]
        if flagged + n <= m:
            flagged += n
            tp += pos
        else:
            take = m - flagged
            tp += pos * take / n  # pro-rata inside the tie block
            flagged = m
            break
    if flagged == 0:
        return 0.0, 0.0, 0
    return tp / total_pos, tp / flagged, flagged


def _lead_days(b):
    return max(0.0, (b.reservation_at - b.created_at).total_seconds()) / 86400


def baseline_scorers(train_bookings):
    """The three sensible baselines from the PRD. Rates come from TRAIN only."""
    outcomes = [b for b in train_bookings if b.status in ("completed", "no_show")]
    party_rate, lead_rate = {}, {}
    counts_p, counts_l = {}, {}
    for b in outcomes:
        pb, lb, _ = booking_features(b)
        np_, kp = counts_p.get(pb, (0, 0))
        counts_p[pb] = (np_ + 1, kp + (b.status == "no_show"))
        nl, kl = counts_l.get(lb, (0, 0))
        counts_l[lb] = (nl + 1, kl + (b.status == "no_show"))
    for band, (n, k) in counts_p.items():
        party_rate[band] = k / n
    for band, (n, k) in counts_l.items():
        lead_rate[band] = k / n

    def rule(b):
        return 1.0 if b.party_size >= 6 or _lead_days(b) > 7 else 0.0

    def party_only(b):
        return party_rate.get(booking_features(b)[0], 0.0)

    def lead_only(b):
        return lead_rate.get(booking_features(b)[1], 0.0)

    return {"rule party>=6 OR lead>7d": rule,
            "party-size-alone": party_only,
            "lead-time-alone": lead_only}


def evaluate(model, train_bookings, test_bookings):
    """Model must arrive already fitted and configured — nothing in here tunes
    anything. Returns a plain-dict report."""
    if model.table is None:
        raise ValueError("evaluate() requires an already-fitted model")
    table_snapshot = dict(model.table)

    eligible = [b for b in test_bookings if b.status in ("completed", "no_show")]
    excluded_cancelled = len(test_bookings) - len(eligible)
    labels = {b.booking_id: 1 if b.status == "no_show" else 0 for b in eligible}
    scored = {b.booking_id: model.score_booking(b) for b in eligible}
    positives = sum(labels.values())

    model_pairs = [(scored[b.booking_id].probability, labels[b.booking_id]) for b in eligible]

    # Baselines: same test rows, same metrics.
    baselines = {}
    scorers = baseline_scorers(train_bookings)
    rule_flag_count = sum(1 for b in eligible if scorers["rule party>=6 OR lead>7d"](b) == 1.0)
    for name, fn in scorers.items():
        pairs = [(fn(b), labels[b.booking_id]) for b in eligible]
        r, p, _ = recall_and_precision_at_flag_count(pairs, rule_flag_count)
        baselines[name] = {"ap": average_precision(pairs),
                           "recall_at_matched_flags": r,
                           "precision_at_matched_flags": p}
    model_r, model_p, _ = recall_and_precision_at_flag_count(model_pairs, rule_flag_count)

    # Operating points: what the product actually does.
    def operating_point(flag_fn):
        flagged = [b for b in eligible if flag_fn(scored[b.booking_id])]
        tp = sum(labels[b.booking_id] for b in flagged)
        n = len(flagged)
        precision = tp / n if n else 0.0
        recall = tp / positives if positives else 0.0
        ns_seats = sum(b.party_size for b in flagged if labels[b.booking_id])
        total_ns_seats = sum(b.party_size for b in eligible if labels[b.booking_id])
        return {
            "flagged": n, "flag_rate": n / len(eligible),
            "true_no_shows": tp, "shows_flagged_anyway": n - tp,
            "precision": precision, "precision_ci": wilson_ci(tp, n),
            "recall": recall, "recall_ci": wilson_ci(tp, positives),
            "no_show_seats_caught": ns_seats,
            "no_show_seats_caught_share": ns_seats / total_ns_seats if total_ns_seats else 0.0,
        }

    # Calibration per bucket (test-side), CI check only where n >= 20.
    calibration = []
    for pb in PARTY_BANDS:
        for lb in LEAD_BANDS:
            in_bucket = [b for b in eligible if (scored[b.booking_id].party_band,
                                                 scored[b.booking_id].lead_band) == (pb, lb)]
            n = len(in_bucket)
            k = sum(labels[b.booking_id] for b in in_bucket)
            predicted = model.table[(pb, lb)][0]
            lo, hi = wilson_ci(k, n)
            calibration.append({
                "bucket": f"{pb} x {lb}", "n": n, "observed": k / n if n else None,
                "predicted": predicted,
                "within_ci": (lo <= predicted <= hi) if n >= 20 else None,
            })

    # Fairness slices: flag rate and precision by party band and by channel.
    def slice_by(key_fn):
        out = {}
        for b in eligible:
            key = key_fn(b)
            row = out.setdefault(key, {"n": 0, "flagged": 0, "flagged_true": 0})
            row["n"] += 1
            if scored[b.booking_id].tier != "LOW":
                row["flagged"] += 1
                row["flagged_true"] += labels[b.booking_id]
        for row in out.values():
            row["flag_rate"] = row["flagged"] / row["n"]
            row["precision"] = row["flagged_true"] / row["flagged"] if row["flagged"] else None
        return out

    assert model.table == table_snapshot, "evaluation must not mutate the model"

    return {
        "split_at": SPLIT_AT.strftime("%Y-%m-%d %H:%M"),
        "train_size": len(train_bookings), "test_size": len(test_bookings),
        "excluded_cancelled_from_eval": excluded_cancelled,
        "eligible": len(eligible), "positives": positives,
        "small_sample_warning": positives < MIN_TEST_POSITIVES,
        "model": {"ap": average_precision(model_pairs),
                  "recall_at_matched_flags": model_r,
                  "precision_at_matched_flags": model_p,
                  "matched_flag_count": rule_flag_count},
        "baselines": baselines,
        "operating_points": {
            "MEDIUM+HIGH": operating_point(lambda s: s.tier != "LOW"),
            "HIGH only": operating_point(lambda s: s.tier == "HIGH"),
        },
        "calibration": calibration,
        "fairness": {"by_party_band": slice_by(lambda b: booking_features(b)[0]),
                     "by_channel": slice_by(lambda b: b.channel)},
    }


def _pct(x):
    return f"{x:.1%}"


def _ci(ci):
    return f"[{ci[0]:.1%} .. {ci[1]:.1%}]"


BAR = "=" * 68
SUB = "-" * 68


def render_report(rep):
    m = rep["model"]
    k = m["matched_flag_count"]
    pos = rep["positives"]
    L = [BAR, " NO-SHOW SHIELD — HONEST BACKTEST", BAR]
    L += [
        f" The model learned ONLY from bookings created up to {rep['split_at']},",
        " and is graded ONLY on later bookings it has never seen — like",
        " studying with old exams, then sitting a brand-new one.",
        "",
        f"   bookings it learned from : {rep['train_size']}",
        f"   bookings it is graded on : {rep['test_size']} (the 'new exam': April)",
        f"   ... of which have a real outcome : {rep['eligible']}",
        f"       ({rep['excluded_cancelled_from_eval']} cancelled excluded — a cancellation is neither",
        "        a show nor a no-show, so it cannot be graded)",
        f"   actual no-shows among those      : {pos} ({_pct(pos / rep['eligible'])})",
        "",
        " Wherever you see 'n' below, it means: how many bookings are in",
        " that group. Small groups wobble — judge them gently.",
    ]
    if rep["small_sample_warning"]:
        L += ["",
              f" !! WARNING: fewer than {MIN_TEST_POSITIVES} real no-shows in the test window —",
              "    every number below is too fragile to lean on."]

    L += ["", SUB, " 1) DOES THE MODEL BEAT THE FREE ALTERNATIVES?", SUB,
          " A manager could apply a simple free rule today (e.g. 'flag big",
          " parties and far-ahead bookings'). If the model can't beat the",
          " free rules, it shouldn't exist. Two scores per contender:",
          "",
          "   PR-AUC ....... one number from 0 to 1: how well the contender",
          "                  ranks risky bookings above safe ones, across all",
          "                  possible cut-offs. Higher is better.",
          f"   at {k} flags .. every contender flags the same {k} bookings",
          "                  (the number the simple rule flags). Then:",
          f"                  recall    = of the {pos} real no-shows, how many it flagged",
          "                  precision = of its flags, how many were real no-shows",
          ""]

    def contender(name, d, mark=""):
        return (f"   {name:27} PR-AUC {d['ap']:.3f}   recall {_pct(d['recall_at_matched_flags']):>6}"
                f"   precision {_pct(d['precision_at_matched_flags']):>6}{mark}")

    L.append(contender("model (bucket table)", m, "   <-- ours"))
    for name, b in rep["baselines"].items():
        L.append(contender(name, b))

    L += ["", SUB, " 2) WHAT WOULD APRIL HAVE LOOKED LIKE WITH THE PRODUCT ON?", SUB,
          " Ranges like [a% .. b%] are honest uncertainty: with only",
          f" {pos} real no-shows to grade on, the truth sits somewhere inside.",
          ""]
    labels = {
        "MEDIUM+HIGH": "we act on MEDIUM and HIGH (SMS re-confirm and up)",
        "HIGH only": "we act on HIGH only (the deposit tier)",
    }
    for op_name, op in rep["operating_points"].items():
        L += [f" If {labels.get(op_name, op_name)}:",
              f"   bookings flagged        : {op['flagged']} of {rep['eligible']} ({_pct(op['flag_rate'])})",
              f"   no-shows caught         : {op['true_no_shows']} of {pos}"
              f"  -> recall {_pct(op['recall'])} {_ci(op['recall_ci'])}",
              f"   flags that were justified: {_pct(op['precision'])} {_ci(op['precision_ci'])} (precision)",
              f"   seats rescued from no-shows: {op['no_show_seats_caught']}"
              f" ({_pct(op['no_show_seats_caught_share'])} of all seats lost to no-shows)",
              f"   the cost                : {op['shows_flagged_anyway']} flagged guests actually showed up",
              ""]

    L += [SUB, " 3) CAN YOU TRUST THE PERCENTAGES? (calibration)", SUB,
          " The model says 'bookings like this no-show X% of the time'.",
          " Here its X (predicted) meets what April actually did (observed).",
          " 'ok' = the observed rate sits inside the honest uncertainty",
          " range of the prediction. Groups with under 20 bookings are",
          " marked 'too small to judge' rather than pretending.",
          "",
          "  group = party size x how far ahead it was booked",
          "  ('1-2 x <1d' = a 1-2 person booking made less than a day ahead)",
          "",
          f"  {'group':16} {'n':>4}  {'predicted':>9}  {'observed':>8}  verdict"]
    for c in rep["calibration"]:
        if c["n"] == 0:
            continue
        obs = _pct(c["observed"]) if c["observed"] is not None else "-"
        ok = {True: "ok", False: "OFF — investigate", None: "too small to judge"}[c["within_ci"]]
        L.append(f"  {c['bucket']:16} {c['n']:>4}  {_pct(c['predicted']):>9}  {obs:>8}  {ok}")

    L += ["", SUB, " 4) WHO PAYS THE FALSE-ALARM COST? (fairness)", SUB,
          " For each group of guests:",
          "   flag rate = what share of their bookings we would bother",
          "               (SMS or more)",
          "   precision = how often bothering them was justified",
          " This makes the cost of false alarms visible per group instead",
          " of hiding it inside an average. (Channel is never used by the",
          " model — it is shown here purely to check who gets bothered.)",
          ""]
    titles = {"by_party_band": "by party size", "by_channel": "by booking channel"}
    for dim, rows in rep["fairness"].items():
        L.append(f"  {titles.get(dim, dim)}:")
        for key in sorted(rows):
            r = rows[key]
            prec = _pct(r["precision"]) if r["precision"] is not None else "-"
            L.append(f"    {key:18} n={r['n']:4}   flag rate {_pct(r['flag_rate']):>6}   precision {prec:>6}")
        L.append("")
    return "\n".join(L)
