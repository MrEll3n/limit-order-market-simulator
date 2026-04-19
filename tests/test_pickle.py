"""
Tests for save_data() and load_data() in server.py.

Verifies that the server state (order books, order history, user balances,
users, ID counter) is correctly persisted to and restored from a pickle file.
"""

import glob as glob_module
import json
import os
import pickle
import sys
import tempfile
import time
import unittest
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root / "src"))

# Required env vars must be set before server.py is imported (it calls _validate_env() at module level)
os.environ.setdefault("JWT_SECRET", "test_jwt_secret")
os.environ.setdefault("COOKIE_SECRET", "test_cookie_secret")
os.environ.setdefault("ALLOWED_EMAIL_DOMAINS", "test.com")
os.environ.setdefault("HOST", "http://localhost")
os.environ.setdefault("PORT", "8888")
os.environ.setdefault("HTTPS", "false")
os.environ.setdefault("CORS_ORIGIN", "http://localhost:3000")
os.environ.setdefault("BOT_PASSWORD", "test_bot_password")
os.environ.setdefault("MARKET_MAKER_EMAIL", "mm@test.com")
os.environ.setdefault("MARKET_MAKER_PASSWORD", "test_mm_password")
os.environ.setdefault("LIQUIDITY_GENERATOR_EMAIL", "lg@test.com")
os.environ.setdefault("LIQUIDITY_GENERATOR_PASSWORD", "test_lg_password")

import server.server as srv
from order_book.order import Order
from order_book.product_manager import TradingProductManager
from server.user_manager import UserManager


def _reset_server_state():
    srv.product_manager = TradingProductManager(srv.products)
    srv.user_manager = UserManager()
    srv.ID = 0


def _setup_test_state():
    """Populate product_manager and user_manager with a known state."""
    _reset_server_state()

    srv.user_manager.add_user("alice", "alice_id", 10000)
    srv.user_manager.add_user("bob", "bob_id", 5000)

    for product in srv.products:
        ob = srv.product_manager.get_order_book(product, False)

        ob.add_order(Order("1", 0, "alice_id", "buy", 10, 100.0))
        ob.add_order(Order("2", 0, "bob_id", "sell", 5, 105.0))

        ob.user_balance["alice_id"] = {"balance": 500.0, "volume": 10, "post_sell_volume": 0}
        ob.user_balance["bob_id"] = {"balance": -200.0, "volume": 5, "post_sell_volume": 5}

        # One historical snapshot
        srv.product_manager.historical_order_books[product].append(
            ob.copy().jsonify_order_book()
        )

    srv.ID = 3


class TestPickleSaveLoad(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_data_dir = srv.DATA_DIR
        srv.DATA_DIR = Path(self._tmpdir.name)
        _setup_test_state()

    def tearDown(self):
        srv.DATA_DIR = self._orig_data_dir
        self._tmpdir.cleanup()
        _reset_server_state()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _snapshot(self):
        """Return a comparable snapshot of the current server state."""
        snap = {"id": srv.ID, "users": {}, "products": {}}
        for uid, u in srv.user_manager.users.items():
            snap["users"][uid] = {"name": u.name, "budget": u.budget}
        for product in srv.products:
            ob = srv.product_manager.get_order_book(product, False)
            snap["products"][product] = {
                "order_book": json.loads(ob.jsonify_order_book()),
                "order_history": ob.order_history,
                "history_len": len(srv.product_manager.historical_order_books[product]),
            }
        return snap

    # ------------------------------------------------------------------
    # tests
    # ------------------------------------------------------------------

    def test_save_and_load_restores_full_state(self):
        before = self._snapshot()

        srv.save_data()
        _reset_server_state()
        srv.load_data()

        after = self._snapshot()

        for product in srv.products:
            b = before["products"][product]
            a = after["products"][product]

            self.assertEqual(a["order_book"]["Bids"], b["order_book"]["Bids"],
                             f"{product}: Bids differ after load")
            self.assertEqual(a["order_book"]["Asks"], b["order_book"]["Asks"],
                             f"{product}: Asks differ after load")
            self.assertEqual(a["order_book"]["UserBalance"], b["order_book"]["UserBalance"],
                             f"{product}: UserBalance differs after load")
            self.assertEqual(a["order_book"]["Timestamp"], b["order_book"]["Timestamp"],
                             f"{product}: Timestamp differs after load")
            self.assertEqual(a["order_history"], b["order_history"],
                             f"{product}: order_history differs after load")
            self.assertEqual(a["history_len"], b["history_len"],
                             f"{product}: historical snapshots count differs after load")

        self.assertEqual(after["users"], before["users"], "Users differ after load")
        self.assertEqual(after["id"], before["id"], "ID counter differs after load")

    def test_load_picks_latest_pickle_file(self):
        """load_data() should restore from the most recently saved file."""
        # Save an initial state, then change state and save again.
        srv.save_data()
        time.sleep(1)  # ensure different filename timestamp

        srv.user_manager.add_user("carol", "carol_id", 9999)
        srv.save_data()

        _reset_server_state()
        srv.load_data()

        self.assertIn("carol_id", srv.user_manager.users,
                      "Should have loaded the latest pickle (with carol)")

    def test_load_skips_unknown_product(self):
        """Products in the pickle that are not in the current config are skipped,
        and the remaining known products are still restored correctly."""
        srv.save_data()

        # Inject an unknown product into the pickle file
        files = sorted(glob_module.glob(str(srv.DATA_DIR / "*-server_data.pickle")))
        with open(files[-1], "rb") as f:
            data = pickle.load(f)
        data["unknown_product_xyz"] = data[srv.products[0]]
        with open(files[-1], "wb") as f:
            pickle.dump(data, f)

        _reset_server_state()
        srv.load_data()  # must not raise

        # Known products should still be restored
        for product in srv.products:
            ob = srv.product_manager.get_order_book(product, False)
            total_orders = len(ob.bids) + len(ob.asks)
            self.assertGreater(total_orders, 0,
                               f"{product} should have orders after load despite unknown product in pickle")

    def test_load_with_no_files_starts_fresh(self):
        """load_data() with an empty data directory should not crash and leave
        state at its initial (empty) values."""
        # Do not save anything — DATA_DIR is empty
        _reset_server_state()
        srv.load_data()  # must not raise

        self.assertEqual(srv.ID, 0)
        for product in srv.products:
            ob = srv.product_manager.get_order_book(product, False)
            self.assertEqual(len(ob.bids), 0)
            self.assertEqual(len(ob.asks), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
