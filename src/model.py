"""Calibrated bucket model: party-size band x lead-time band -> no-show probability.

Fully interpretable — the whole model is a 4x4 table, every cell a sentence.
Sparse cells shrink toward the average of the two band marginals so scoring
never divides by zero and thin cells don't produce wild estimates.
"""
import datetime as dt
from dataclasses import dataclass

from .features import PARTY_BANDS, LEAD_BANDS, compute_features

SHRINK_K = 20        # pseudo-count pulled toward the band-marginal prior
MIN_SUPPORT = 20     # below this a cell is marked sparse (reason says so)

# Half-open [lo, hi): p=0.10 -> MEDIUM, p=0.35 -> HIGH. Policy dials from the
# PRD, fixed before any test data was read.
TIER_BOUNDS = (("LOW", 0.0, 0.10), ("MEDIUM", 0.10, 0.35), ("HIGH", 0.35, 1.01))

LARGE_PARTY = 6

ACTIONS = {
    "NONE": "No action — keep the booking frictionless.",
    "SMS_CONFIRM": "Send SMS/WhatsApp re-confirmation with one-tap cancel ~24h before the slot.",
    "CONFIRM_ONLY": "Re-confirm by SMS/call (no deposit — deposits are reserved for large parties).",
    "CONFIRM_PLUS_DEPOSIT": "Re-confirm + request refundable deposit / card hold (auto-released on re-confirm).",
}


def tier_for(probability):
    for name, lo, hi in TIER_BOUNDS:
        if lo <= probability < hi:
            return name
    raise ValueError(f"probability out of range: {probability}")


def action_for(tier, party_size):
    if tier == "LOW":
        return "NONE"
    if tier == "MEDIUM":
        return "SMS_CONFIRM"
    return "CONFIRM_PLUS_DEPOSIT" if party_size >= LARGE_PARTY else "CONFIRM_ONLY"


@dataclass(frozen=True)
class Scored:
    booking_id: str | None
    party_size: int
    party_band: str
    lead_band: str
    lead_hours: float
    probability: float
    sparse: bool
    tier: str
    reason: str
    action: str
    action_text: str


class BucketModel:
    def __init__(self):
        self.table = None  # (party_band, lead_band) -> (probability, n, sparse)

    def fit(self, train_bookings):
        """Fit from training bookings only. Cancelled rows carry no show/no-show
        outcome and are excluded."""
        outcomes = [b for b in train_bookings if b.status in ("completed", "no_show")]
        if not outcomes:
            raise ValueError("no completed/no_show bookings to fit on")
        cell_n, cell_ns = {}, {}
        party_n, party_ns, lead_n, lead_ns = {}, {}, {}, {}
        total_ns = 0
        for b in outcomes:
            pb, lb, _ = compute_features({
                "party_size": b.party_size,
                "created_at": b.created_at,
                "reservation_at": b.reservation_at,
            })
            is_ns = b.status == "no_show"
            cell_n[(pb, lb)] = cell_n.get((pb, lb), 0) + 1
            cell_ns[(pb, lb)] = cell_ns.get((pb, lb), 0) + is_ns
            party_n[pb] = party_n.get(pb, 0) + 1
            party_ns[pb] = party_ns.get(pb, 0) + is_ns
            lead_n[lb] = lead_n.get(lb, 0) + 1
            lead_ns[lb] = lead_ns.get(lb, 0) + is_ns
            total_ns += is_ns
        global_rate = total_ns / len(outcomes)

        def marginal(ns, n, key):
            return ns[key] / n[key] if n.get(key) else global_rate

        self.table = {}
        for pb in PARTY_BANDS:
            for lb in LEAD_BANDS:
                n = cell_n.get((pb, lb), 0)
                ns = cell_ns.get((pb, lb), 0)
                prior = (marginal(party_ns, party_n, pb) + marginal(lead_ns, lead_n, lb)) / 2
                p = (ns + SHRINK_K * prior) / (n + SHRINK_K)
                self.table[(pb, lb)] = (p, n, n < MIN_SUPPORT)
        return self

    def score(self, party_size, created_at, reservation_at, booking_id=None):
        if self.table is None:
            raise ValueError("model is not fitted")
        pb, lb, lead_hours = compute_features({
            "party_size": party_size,
            "created_at": created_at,
            "reservation_at": reservation_at,
        })
        p, n, sparse = self.table[(pb, lb)]
        tier = tier_for(p)
        action = action_for(tier, party_size)
        if lead_hours < 24:
            when = f"booked {int(lead_hours)} hours ahead"
        else:
            when = f"booked {round(lead_hours / 24)} days ahead"
        reason = (
            f"party of {party_size}, {when}; "
            f"similar bookings no-showed {p:.0%} of the time"
        )
        if sparse:
            reason += " (limited history for this combination)"
        return Scored(
            booking_id=booking_id, party_size=party_size, party_band=pb,
            lead_band=lb, lead_hours=lead_hours, probability=p, sparse=sparse,
            tier=tier, reason=reason, action=action, action_text=ACTIONS[action],
        )

    def score_booking(self, booking):
        return self.score(booking.party_size, booking.created_at,
                          booking.reservation_at, booking_id=booking.booking_id)
