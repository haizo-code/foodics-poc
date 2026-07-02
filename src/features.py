"""Feature construction with a structural leakage guard.

The only fields that may ever reach the model are party_size, created_at and
reservation_at — everything else (outcome fields, identity fields, channel) is
rejected at the door, so leakage cannot be introduced by future edits either.
"""

ALLOWED = frozenset({"party_size", "created_at", "reservation_at"})

# Half-open bands [lo, hi): exactly 24h -> "1-3d", exactly 7*24h -> ">7d".
PARTY_BANDS = ("1-2", "3-4", "5", "6+")
LEAD_BANDS = ("<1d", "1-3d", "3-7d", ">7d")


class LeakageError(ValueError):
    """Raised when anything beyond the allowed at-creation-time fields reaches features."""


def party_band(party_size):
    if party_size <= 2:
        return "1-2"
    if party_size <= 4:
        return "3-4"
    if party_size == 5:
        return "5"
    return "6+"  # unbounded top band: party 15 clamps here naturally


def lead_band(lead_hours):
    if lead_hours < 24:
        return "<1d"
    if lead_hours < 72:
        return "1-3d"
    if lead_hours < 168:
        return "3-7d"
    return ">7d"  # unbounded top band: 60d clamps here naturally


def compute_features(fields):
    """fields must be exactly {party_size, created_at, reservation_at}.

    Passing a record that carries anything else — status, cancelled_at, names,
    phones, channel — raises LeakageError."""
    if set(fields) != ALLOWED:
        raise LeakageError(
            f"feature input must be exactly {sorted(ALLOWED)}, got {sorted(fields)}"
        )
    party = fields["party_size"]
    if type(party) is not int or party < 1:
        raise ValueError(f"party_size must be a positive integer, got {party!r}")
    lead_hours = (fields["reservation_at"] - fields["created_at"]).total_seconds() / 3600
    lead_hours = max(0.0, lead_hours)  # clamp clock skew; never a negative feature
    return party_band(party), lead_band(lead_hours), lead_hours


def booking_features(booking):
    return compute_features({
        "party_size": booking.party_size,
        "created_at": booking.created_at,
        "reservation_at": booking.reservation_at,
    })
