"""Thin local demo: worklist | score | backtest.

  python3 -m src.demo worklist              # triage list of upcoming high-risk bookings
  python3 -m src.demo score --party 8 --when "2026-05-14 20:00"
  python3 -m src.demo backtest              # honest train-Jan-Mar / test-April backtest
"""
import argparse
import datetime as dt

from .ingest import load_bookings, FMT
from .model import BucketModel
from .evaluate import time_split, evaluate, render_report

CSV = "bookings.csv"


def _fitted(path):
    bookings, flags = load_bookings(path)
    train, test = time_split(bookings)
    model = BucketModel().fit(train)
    return bookings, flags, train, test, model


def cmd_worklist(args):
    _, _, _, test, model = _fitted(args.csv)
    upcoming = [b for b in test if b.status != "cancelled"]  # cancelled already freed the table
    scored = [(model.score_booking(b), b) for b in upcoming]
    scored = [t for t in scored if t[0].tier != "LOW"]
    scored.sort(key=lambda t: t[0].probability, reverse=True)
    scored = scored[:args.top]
    print(f"Triage worklist — top {len(scored)} at-risk upcoming bookings "
          f"(demo 'today' = split date; outcomes hidden, exactly as the host would see it)\n")
    for s, b in scored:
        print(f"{s.tier:6} {b.reservation_at.strftime('%a %d %b %H:%M'):18} "
              f"{b.restaurant_name:16} {s.reason}")
        print(f"{'':6} -> {s.action_text}\n")


def cmd_score(args):
    _, _, _, _, model = _fitted(args.csv)
    now = dt.datetime.strptime(args.now, FMT) if args.now else dt.datetime.now()
    when = dt.datetime.strptime(args.when, FMT)
    s = model.score(args.party, created_at=now, reservation_at=when)
    print(f"tier:   {s.tier}  (estimated no-show probability {s.probability:.0%})")
    print(f"reason: {s.reason}")
    print(f"action: {s.action_text}")


def cmd_backtest(args):
    bookings, flags, train, test, model = _fitted(args.csv)
    if flags:
        print(f"Data quality: {len(flags)} flagged rows "
              f"(e.g., {flags[0][0]}: {flags[0][1]})\n")
    print(render_report(evaluate(model, train, test)))
    print("\nModel (the whole thing — every cell is a sentence):")
    print(f"{'':8}" + "".join(f"{lb:>12}" for lb in ("<1d", "1-3d", "3-7d", ">7d")))
    for pb in ("1-2", "3-4", "5", "6+"):
        row = [f"{model.table[(pb, lb)][0]:>11.0%}" + ("*" if model.table[(pb, lb)][2] else " ")
               for lb in ("<1d", "1-3d", "3-7d", ">7d")]
        print(f"party {pb:3}" + "".join(row))
    print("(* = thin training data, shrunk toward band average)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=CSV)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("worklist")
    w.add_argument("--top", type=int, default=12)
    s = sub.add_parser("score")
    s.add_argument("--party", type=int, required=True)
    s.add_argument("--when", required=True, help='reservation time "YYYY-MM-DD HH:MM"')
    s.add_argument("--now", default=None, help="pretend the booking is created at this time")
    sub.add_parser("backtest")
    args = ap.parse_args()
    {"worklist": cmd_worklist, "score": cmd_score, "backtest": cmd_backtest}[args.cmd](args)


if __name__ == "__main__":
    main()
