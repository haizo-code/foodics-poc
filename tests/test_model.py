import datetime as dt
import unittest

from src.ingest import load_bookings
from src.model import BucketModel, tier_for, action_for, MIN_SUPPORT
from src.evaluate import time_split
from tests.helpers import REAL_CSV, row, write_csv

T0 = dt.datetime(2026, 1, 1, 10, 0)


def fitted_on_real():
    bookings, _ = load_bookings(REAL_CSV)
    train, _ = time_split(bookings)
    return BucketModel().fit(train)


class TestModel(unittest.TestCase):
    def test_MD1_fit_from_train_only_all_cells_valid(self):
        model = fitted_on_real()
        self.assertEqual(len(model.table), 16)
        for (pb, lb), (p, n, sparse) in model.table.items():
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)

    def test_MD2_sparse_cell_falls_back_without_dividing_by_zero(self):
        # 30 bookings all in one cell (party 1-2, lead 1-3d), 10 no-shows
        rows = [row(bid=f"B{i}", party=2, created="2026-01-01 10:00",
                    resv="2026-01-03 10:00",
                    status="no_show" if i < 10 else "completed")
                for i in range(30)]
        bookings, _ = load_bookings(write_csv(rows))
        model = BucketModel().fit(bookings)
        # the empty cell gets the band-marginal prior (here = global rate) and is sparse
        p_empty, n_empty, sparse_empty = model.table[("6+", ">7d")]
        self.assertEqual(n_empty, 0)
        self.assertTrue(sparse_empty)
        self.assertAlmostEqual(p_empty, 10 / 30, places=6)
        # the populated cell shrinks toward the same prior: (10 + 20*(1/3)) / (30 + 20)
        p_full, n_full, _ = model.table[("1-2", "1-3d")]
        self.assertEqual(n_full, 30)
        self.assertAlmostEqual(p_full, (10 + 20 * (10 / 30)) / 50, places=6)

    def test_MD3_fitted_table_reflects_the_known_gradient(self):
        model = fitted_on_real()
        p = {k: v[0] for k, v in model.table.items()}
        self.assertGreater(p[("6+", ">7d")], p[("6+", "<1d")])
        self.assertGreater(p[("6+", ">7d")], p[("1-2", ">7d")])
        self.assertGreater(p[("1-2", ">7d")], p[("1-2", "<1d")])

    def test_MD4_tier_boundaries_half_open(self):
        self.assertEqual(tier_for(0.0), "LOW")
        self.assertEqual(tier_for(0.099), "LOW")
        self.assertEqual(tier_for(0.10), "MEDIUM")
        self.assertEqual(tier_for(0.349), "MEDIUM")
        self.assertEqual(tier_for(0.35), "HIGH")
        self.assertEqual(tier_for(1.0), "HIGH")

    def test_MD5_reason_contains_party_lead_and_rate(self):
        model = fitted_on_real()
        s = model.score(8, T0, T0 + dt.timedelta(days=12))
        self.assertIn("party of 8", s.reason)
        self.assertIn("12 days ahead", s.reason)
        self.assertIn("%", s.reason)
        # same-day bookings speak in hours
        s2 = model.score(2, T0, T0 + dt.timedelta(hours=5))
        self.assertIn("5 hours ahead", s2.reason)

    def test_MD6_action_mapping_deposits_large_parties_only(self):
        self.assertEqual(action_for("LOW", 8), "NONE")
        self.assertEqual(action_for("MEDIUM", 8), "SMS_CONFIRM")
        self.assertEqual(action_for("HIGH", 8), "CONFIRM_PLUS_DEPOSIT")
        self.assertEqual(action_for("HIGH", 6), "CONFIRM_PLUS_DEPOSIT")
        # HIGH but small party: never a deposit
        self.assertEqual(action_for("HIGH", 4), "CONFIRM_ONLY")
        self.assertEqual(action_for("HIGH", 1), "CONFIRM_ONLY")

    def test_MD7_deterministic(self):
        m1, m2 = fitted_on_real(), fitted_on_real()
        self.assertEqual(m1.table, m2.table)
        a = m1.score(6, T0, T0 + dt.timedelta(days=10))
        b = m1.score(6, T0, T0 + dt.timedelta(days=10))
        self.assertEqual(a, b)

    def test_DQ6_garbage_party_size_rejected_at_scoring(self):
        model = fitted_on_real()
        for bad in (0, -2, 2.5, "two", True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                model.score(bad, T0, T0 + dt.timedelta(days=1))

    def test_unfitted_model_refuses_to_score(self):
        with self.assertRaises(ValueError):
            BucketModel().score(2, T0, T0 + dt.timedelta(days=1))


if __name__ == "__main__":
    unittest.main()
