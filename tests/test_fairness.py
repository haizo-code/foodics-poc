import dataclasses
import unittest

from src.ingest import load_bookings
from src.model import BucketModel
from src.evaluate import time_split, evaluate
from tests.helpers import REAL_CSV


class TestFairness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bookings, _ = load_bookings(REAL_CSV)
        cls.train, cls.test = time_split(bookings)
        cls.model = BucketModel().fit(cls.train)
        cls.rep = evaluate(cls.model, cls.train, cls.test)

    def test_FA1_fairness_slices_present(self):
        fairness = self.rep["fairness"]
        self.assertIn("by_party_band", fairness)
        self.assertIn("by_channel", fairness)
        self.assertEqual(set(fairness["by_channel"]),
                         {"foodics_app", "phone", "website", "partner_platform"})
        for rows in fairness.values():
            for r in rows.values():
                self.assertIn("flag_rate", r)
                self.assertIn("precision", r)

    def test_FA2_channel_never_changes_a_score(self):
        for b in self.test[:200]:
            swapped = dataclasses.replace(
                b, channel="phone" if b.channel != "phone" else "website")
            a = self.model.score_booking(b)
            c = self.model.score_booking(swapped)
            self.assertEqual(a.probability, c.probability, b.booking_id)
            self.assertEqual(a.tier, c.tier, b.booking_id)


if __name__ == "__main__":
    unittest.main()
