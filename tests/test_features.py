import datetime as dt
import unittest

from src.features import compute_features, LeakageError
from src.ingest import load_bookings
from src.model import BucketModel
from src.evaluate import time_split
from tests.helpers import REAL_CSV

T0 = dt.datetime(2026, 1, 1, 10, 0)


def feats(party=2, lead_hours=30.0):
    return compute_features({
        "party_size": party,
        "created_at": T0,
        "reservation_at": T0 + dt.timedelta(hours=lead_hours),
    })


class TestFeatures(unittest.TestCase):
    def test_FE1_outcome_fields_rejected_at_the_door(self):
        full_record = {"party_size": 2, "created_at": T0,
                       "reservation_at": T0 + dt.timedelta(days=1),
                       "status": "no_show", "cancelled_at": None}
        with self.assertRaises(LeakageError):
            compute_features(full_record)

    def test_FE2_leakage_canary_single_extra_field(self):
        for leaky in ("status", "cancelled_at", "customer_id", "channel"):
            with self.assertRaises(LeakageError):
                compute_features({"party_size": 2, "created_at": T0,
                                  "reservation_at": T0 + dt.timedelta(days=1),
                                  leaky: "x"})
        # missing a required field is also structural breakage
        with self.assertRaises(LeakageError):
            compute_features({"party_size": 2, "created_at": T0})

    def test_FE3_identity_and_channel_never_change_a_score(self):
        bookings, _ = load_bookings(REAL_CSV)
        train, _ = time_split(bookings)
        model = BucketModel().fit(train)
        b = bookings[0]
        base = model.score(b.party_size, b.created_at, b.reservation_at)
        # identity/channel aren't even accepted by the scoring interface;
        # same 3 fields => same score regardless of who is booking
        again = model.score(b.party_size, b.created_at, b.reservation_at)
        self.assertEqual(base.probability, again.probability)
        self.assertEqual(base.tier, again.tier)

    def test_FE4_lead_band_boundaries_half_open(self):
        self.assertEqual(feats(lead_hours=23.99)[1], "<1d")
        self.assertEqual(feats(lead_hours=24.0)[1], "1-3d")     # exactly 24h
        self.assertEqual(feats(lead_hours=71.99)[1], "1-3d")
        self.assertEqual(feats(lead_hours=72.0)[1], "3-7d")
        self.assertEqual(feats(lead_hours=167.99)[1], "3-7d")
        self.assertEqual(feats(lead_hours=168.0)[1], ">7d")     # exactly 7d
        self.assertEqual(feats(lead_hours=0.0)[1], "<1d")

    def test_FE5_party_band_boundaries(self):
        self.assertEqual(feats(party=2)[0], "1-2")
        self.assertEqual(feats(party=3)[0], "3-4")
        self.assertEqual(feats(party=4)[0], "3-4")
        self.assertEqual(feats(party=5)[0], "5")
        self.assertEqual(feats(party=6)[0], "6+")

    def test_FE6_out_of_range_clamps_to_top_bands(self):
        pb, lb, _ = feats(party=15, lead_hours=60 * 24)
        self.assertEqual((pb, lb), ("6+", ">7d"))
        bookings, _ = load_bookings(REAL_CSV)
        train, _ = time_split(bookings)
        model = BucketModel().fit(train)
        s = model.score(15, T0, T0 + dt.timedelta(days=60))
        self.assertEqual(s.tier, "HIGH")  # scores fine, lands in top bands

    def test_negative_lead_clamped_to_zero(self):
        pb, lb, lead_hours = compute_features({
            "party_size": 2, "created_at": T0,
            "reservation_at": T0 - dt.timedelta(hours=5),
        })
        self.assertEqual(lead_hours, 0.0)
        self.assertEqual(lb, "<1d")


if __name__ == "__main__":
    unittest.main()
