import datetime as dt
import unittest

from src.ingest import load_bookings
from src.evaluate import time_split, SPLIT_AT, evaluate, MIN_TEST_POSITIVES
from src.model import BucketModel
from tests.helpers import REAL_CSV, row, write_csv


class TestSplit(unittest.TestCase):
    def test_SP1_split_is_strictly_temporal_and_complete(self):
        bookings, _ = load_bookings(REAL_CSV)
        train, test = time_split(bookings)
        self.assertLess(max(b.created_at for b in train), min(b.created_at for b in test))
        self.assertEqual(len(train) + len(test), 2600)
        train_ids = {b.booking_id for b in train}
        self.assertTrue(all(b.booking_id not in train_ids for b in test))

    def test_SP2_boundary_booking_goes_to_train(self):
        path = write_csv([
            row(bid="AT", created=SPLIT_AT.strftime("%Y-%m-%d %H:%M"), resv="2026-04-05 20:00"),
            row(bid="AFTER", created=(SPLIT_AT + dt.timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"),
                resv="2026-04-05 21:00"),
        ])
        bookings, _ = load_bookings(path)
        train, test = time_split(bookings)
        self.assertEqual([b.booking_id for b in train], ["AT"])
        self.assertEqual([b.booking_id for b in test], ["AFTER"])

    def test_SP3_small_sample_warning(self):
        bookings, _ = load_bookings(REAL_CSV)
        train, test = time_split(bookings)
        model = BucketModel().fit(train)
        rep = evaluate(model, train, test)
        self.assertGreaterEqual(rep["positives"], MIN_TEST_POSITIVES)
        self.assertFalse(rep["small_sample_warning"])
        # a tiny test window must warn instead of silently reporting fragile numbers
        tiny = ([b for b in test if b.status == "completed"][:15]
                + [b for b in test if b.status == "no_show"][:3])
        rep_tiny = evaluate(model, train, tiny)
        self.assertTrue(rep_tiny["small_sample_warning"])


if __name__ == "__main__":
    unittest.main()
