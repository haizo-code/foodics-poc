"""Shared fixtures: real CSV path + a tiny synthetic-CSV builder."""
import os
import tempfile

REAL_CSV = os.path.join(os.path.dirname(__file__), "..", "bookings.csv")

HEADER = ("booking_id,restaurant_id,restaurant_name,customer_id,customer_name,"
          "customer_phone,party_size,channel,created_at,reservation_at,status,cancelled_at")


def row(bid="B1", party=2, created="2026-01-01 10:00", resv="2026-01-02 20:00",
        status="completed", cancelled="", channel="foodics_app", customer="C1"):
    return (f"{bid},R01,Test House,{customer},Guest,+966500000000,"
            f"{party},{channel},{created},{resv},{status},{cancelled}")


def write_csv(rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
    f.write(HEADER + "\n" + "\n".join(rows) + "\n")
    f.close()
    return f.name
