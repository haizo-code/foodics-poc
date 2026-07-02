import unittest

from src.ingest import load_bookings
from tests.helpers import REAL_CSV, row, write_csv


class TestIngest(unittest.TestCase):
    def test_DQ1_real_csv_parses(self):
        bookings, _ = load_bookings(REAL_CSV)
        self.assertEqual(len(bookings), 2600)
        self.assertEqual(len({b.booking_id for b in bookings}), 2600)

    def test_DQ2_cancelled_at_iff_cancelled(self):
        bookings, _ = load_bookings(REAL_CSV)
        for b in bookings:
            self.assertEqual(b.status == "cancelled", b.cancelled_at is not None, b.booking_id)
        # violations in synthetic data are rejected
        with self.assertRaises(ValueError):
            load_bookings(write_csv([row(status="completed", cancelled="2026-01-01 12:00")]))
        with self.assertRaises(ValueError):
            load_bookings(write_csv([row(status="cancelled", cancelled="")]))

    def test_DQ3_clock_skew_rows_flagged_not_dropped(self):
        bookings, flags = load_bookings(REAL_CSV)
        skew = [f for f in flags if "cancelled_at before created_at" in f[1]]
        self.assertEqual(len(skew), 5)  # the known anomaly in this dataset
        self.assertEqual(len(bookings), 2600)  # kept, not dropped

    def test_DQ4_unknown_status_rejected_with_row_named(self):
        path = write_csv([row(bid="BX", status="maybe")])
        with self.assertRaises(ValueError) as ctx:
            load_bookings(path)
        self.assertIn("BX", str(ctx.exception))
        self.assertIn("maybe", str(ctx.exception))

    def test_DQ5_negative_lead_flagged(self):
        path = write_csv([row(created="2026-01-02 20:00", resv="2026-01-01 10:00")])
        bookings, flags = load_bookings(path)
        self.assertEqual(len(bookings), 1)
        self.assertTrue(any("clamped" in f[1] for f in flags))

    def test_duplicate_booking_id_rejected(self):
        path = write_csv([row(bid="B1"), row(bid="B1")])
        with self.assertRaises(ValueError):
            load_bookings(path)


if __name__ == "__main__":
    unittest.main()
