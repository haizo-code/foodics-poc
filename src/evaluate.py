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
    return f"[{ci[0]:.1%}, {ci[1]:.1%}]"


def render_report(rep):
    L = []
    L.append(f"Time split on created_at at {rep['split_at']} — train {rep['train_size']}, test {rep['test_size']}")
    L.append(f"Evaluated on {rep['eligible']} test bookings with an outcome "
             f"({rep['excluded_cancelled_from_eval']} cancelled excluded — no show/no-show outcome); "
             f"{rep['positives']} no-shows.")
    if rep["small_sample_warning"]:
        L.append(f"WARNING: fewer than {MIN_TEST_POSITIVES} positives — every number below is fragile.")
    L.append("")
    L.append(f"Model vs baselines (recall/precision at the rule's own flag count = {rep['model']['matched_flag_count']}):")
    m = rep["model"]
    L.append(f"  {'model (bucket table)':28} PR-AUC {m['ap']:.3f}  recall {_pct(m['recall_at_matched_flags'])}  precision {_pct(m['precision_at_matched_flags'])}")
    for name, b in rep["baselines"].items():
        L.append(f"  {name:28} PR-AUC {b['ap']:.3f}  recall {_pct(b['recall_at_matched_flags'])}  precision {_pct(b['precision_at_matched_flags'])}")
    L.append("")
    for op_name, op in rep["operating_points"].items():
        L.append(f"Operating point {op_name}: flags {op['flagged']}/{rep['eligible']} ({_pct(op['flag_rate'])})")
        L.append(f"  precision {_pct(op['precision'])} {_ci(op['precision_ci'])}   recall {_pct(op['recall'])} {_ci(op['recall_ci'])}")
        L.append(f"  no-show seats caught: {op['no_show_seats_caught']} ({_pct(op['no_show_seats_caught_share'])} of all no-show seats)")
        L.append(f"  cost: {op['shows_flagged_anyway']} flagged guests actually showed up")
    L.append("")
    L.append("Calibration (predicted vs observed April rate; CI check where n >= 20):")
    for c in rep["calibration"]:
        if c["n"] == 0:
            continue
        obs = _pct(c["observed"]) if c["observed"] is not None else "-"
        ok = {True: "ok", False: "OFF", None: "n too small"}[c["within_ci"]]
        L.append(f"  {c['bucket']:14} n={c['n']:4}  predicted {_pct(c['predicted'])}  observed {obs}  {ok}")
    L.append("")
    L.append("Fairness slices (flag rate / precision of flags):")
    for dim, rows in rep["fairness"].items():
        L.append(f"  {dim}:")
        for key in sorted(rows):
            r = rows[key]
            prec = _pct(r["precision"]) if r["precision"] is not None else "-"
            L.append(f"    {key:20} n={r['n']:4}  flag rate {_pct(r['flag_rate'])}  precision {prec}")
    return "\n".join(L)
