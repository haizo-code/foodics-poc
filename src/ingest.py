"""Load and validate bookings.csv. Returns bookings plus a data-quality report."""
import csv
import datetime as dt
from dataclasses import dataclass

FMT = "%Y-%m-%d %H:%M"
STATUSES = {"completed", "no_show", "cancelled"}
REQUIRED = [
    "booking_id", "restaurant_id", "restaurant_name", "customer_id",
    "customer_name", "customer_phone", "party_size", "channel",
    "created_at", "reservation_at", "status", "cancelled_at",
]


@dataclass(frozen=True)
class Booking:
    booking_id: str
    restaurant_id: str
    restaurant_name: str
    customer_id: str
    customer_name: str
    customer_phone: str
    party_size: int
    channel: str
    created_at: dt.datetime
    reservation_at: dt.datetime
    status: str
    cancelled_at: dt.datetime | None


def load_bookings(path):
    """Returns (bookings, quality_flags). Raises ValueError on structural problems;
    plausible-but-odd rows (clock skew) are kept and flagged, not dropped."""
    bookings, flags, seen_ids = [], [], set()
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"missing columns: {missing}")
        for lineno, row in enumerate(reader, start=2):
            bid = row["booking_id"]
            if not bid or bid in seen_ids:
                raise ValueError(f"row {lineno}: missing or duplicate booking_id {bid!r}")
            seen_ids.add(bid)
            if row["status"] not in STATUSES:
                raise ValueError(f"row {lineno} ({bid}): unknown status {row['status']!r}")
            try:
                party = int(row["party_size"])
            except ValueError:
                raise ValueError(f"row {lineno} ({bid}): party_size {row['party_size']!r} is not an integer")
            if party < 1:
                raise ValueError(f"row {lineno} ({bid}): party_size must be >= 1, got {party}")
            created = dt.datetime.strptime(row["created_at"], FMT)
            resv = dt.datetime.strptime(row["reservation_at"], FMT)
            cancelled = dt.datetime.strptime(row["cancelled_at"], FMT) if row["cancelled_at"] else None
            if (row["status"] == "cancelled") != (cancelled is not None):
                raise ValueError(f"row {lineno} ({bid}): cancelled_at must be set iff status is cancelled")
            if cancelled and cancelled < created:
                flags.append((bid, "cancelled_at before created_at (clock skew?)"))
            if resv < created:
                flags.append((bid, "reservation_at before created_at; lead time will be clamped to 0"))
            bookings.append(Booking(
                booking_id=bid, restaurant_id=row["restaurant_id"],
                restaurant_name=row["restaurant_name"], customer_id=row["customer_id"],
                customer_name=row["customer_name"], customer_phone=row["customer_phone"],
                party_size=party, channel=row["channel"],
                created_at=created, reservation_at=resv,
                status=row["status"], cancelled_at=cancelled,
            ))
    return bookings, flags
