import json
import unittest
import subprocess
import time
import logging
import requests
import colorlog
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.client.algorithmic_trader import AlgorithmicTrader
from src.client.client import AdminTrader

logger = logging.getLogger(__name__)

"""
For the tests to run correctly, the INITIAL_BUDGET set in the server.py must be 10000
"""

# IMPORTANT: Ensure the path to the Python executable is correct
python_path = "path/to/python.exe"  # Update this to the correct path for your environment

class TestAdminTrader(AdminTrader):
    def receive_market_data(self, data):
        pass # Required implementation for abstract class

class TestTrader(AlgorithmicTrader):
    def __init__(self, target, config):
        super().__init__("test_trader", target, config)

    def handle_market_data(self, data):
        pass

    def trade(self, message):
        pass

def configure_test_logging():
    """
    Configure logging specifically for tests to output logs to the console.
    """
    # Create a custom logger for the tests
    test_logger = logging.getLogger()
    test_logger.setLevel(logging.INFO)

    # Create a console handler for the test logs
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    # Create a formatter for the log messages
    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
        datefmt=None,
        reset=True,
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    )
    ch.setFormatter(formatter)

    # Add the console handler to the logger
    test_logger.addHandler(ch)

class TestAlgorithmicTraderIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Set up the test class by configuring logging.
        """
        configure_test_logging()

    def setUp(self):
        """
        Ensure a clean test state before each test.
        Starts the server and initializes the AlgorithmicTrader and TestAdminTrader.
        """
        # Start the server using subprocess
        logger.info("Starting the server...")
        try:
            self.server_process = subprocess.Popen(
                [python_path, "..\src\server\server.py"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # Periodically check if the server has started
            server_started = False
            config = json.load(open(os.path.join(os.path.dirname(__file__), "../config/server_config.json")))
            for _ in range(10):
                try:
                    port = config["PORT"]
                    response = requests.get(f"http://localhost:{port}")
                    if response.status_code == 200:
                        server_started = True
                        break
                except requests.exceptions.ConnectionError:
                    time.sleep(1)

            if not server_started:
                raise Exception("Failed to start the server. Exiting...")

            self.trader = TestTrader("Server1", config)
            self.tester = TestAdminTrader("liquidity_generator", "Server1", config)
            self.tester.register(0)
            self.tester.initialize_liquidity_engine(10000, 10000)
            logger.info("Server started and AlgorithmicTrader initialized.")
        except Exception as e:
            logger.error(f"Error starting the server: {e}")
            raise

    def tearDown(self):
        """
        Ensure the server is stopped after each test.
        """
        self.server_process.terminate()
        self.server_process.wait()

    def register_user(self, budget):
        """
        Registers a new user and returns the user ID.
        """
        user_id = self.trader.register(budget)
        self.assertIsNotNone(user_id, "User registration failed.")
        return user_id

    def test_basic_order_flow(self):
        """
        Scenario 1: Basic Order Flow Validation

        Objective: Validate the end-to-end trading process with a basic order.

        - Register a new user with a budget of 1000.
        - Place a buy order for a product.
        - Check order status.
        - Modify the order price.
        - Delete the order.
        - Verify balance after deletion.
        """
        logger.info("Starting Scenario 1: Basic Order Flow Validation")

        # Register a new user with a budget of 1000
        self.register_user(1000)

        # Place a buy order
        order_details = {"price": 100, "quantity": 5, "side": "buy"}
        order_id, status = self.trader.put_order(order_details, "product1")
        self.assertTrue(status, "Failed to place buy order.")
        self.assertIsNotNone(order_id, "Order ID is None after order placement.")
        logger.info(f"Buy order placed with ID: {order_id}")

        # Validate order status
        order_status = self.trader.order_stats(order_id, "product1")
        self.assertEqual(order_status["price"], 100, "Incorrect order price.")
        self.assertEqual(order_status["quantity"], 5, "Incorrect order quantity.")
        self.assertEqual(order_status["side"], "buy", "Incorrect order side.")
        logger.info(f"Order status verified: {order_status}")

        # Validate that the order appears in the user's active orders
        active_orders = self.trader.list_user_orders("product1")
        self.assertIn(order_id, active_orders, f"Order ID {order_id} not found in active orders.")

        # Modify the order
        new_order_id, status = self.trader.modify_order(order_id, "product1", new_price=110)
        self.assertTrue(status, "Failed to modify order.")
        self.assertIsNotNone(new_order_id, "New Order ID should not be None.")

        # Validate the modified order
        order_status = self.trader.order_stats(new_order_id, "product1")
        self.assertEqual(order_status["price"], 110)
        logger.info(f"Order modified to new price 110. New Order ID: {new_order_id}")

        # Delete the order
        result = self.trader.delete_order(new_order_id, "product1")
        self.assertTrue(result, "Failed to delete order.")
        logger.info(f"Order {new_order_id} deleted successfully.")

        # Ensure the order is removed from the active orders list
        active_orders = self.trader.list_user_orders("product1")
        self.assertNotIn(new_order_id, active_orders, f"Order ID {new_order_id} was not removed from active orders.")

        # Verify user balance (should be unchanged minus any fees)
        balance = self.trader.user_balance("product1", verbose=False)
        self.assertGreaterEqual(balance["post_buy_budget"], 999, "Balance mismatch after order deletion.")
        logger.info(f"Final user balance: {balance}")

        logger.info("Basic order flow validation completed.")

    def test_order_book_management(self):
        """
        Scenario 2: Order Book Management and Validation

        Objective: Test proper management of the order book.

        - Validate empty order book retrieval.
        - Place buy and sell orders.
        - Verify the state of the order book.
        - Validate correct price and priority sorting.
        """
        logger.info("Starting Scenario 2: Order Book Management and Validation")

        # Register a new user only for clean up purposes
        self.register_user(5)

        # Validate empty order book
        order_book = self.tester.order_book_request("product1")
        self.assertEqual(order_book["Asks"], [], "Order book 'asks' is not empty.")
        self.assertEqual(order_book["Bids"], [], "Order book 'bids' is not empty.")
        logger.info("Empty order book verified.")

        # Place sell orders
        self.tester.put_order({"price": 100, "quantity": 10, "side": "sell"}, "product1")
        self.tester.put_order({"price": 101, "quantity": 5, "side": "sell"}, "product1")
        self.tester.put_order({"price": 100, "quantity": 7, "side": "sell"}, "product1")

        # Place buy orders
        self.tester.put_order({"price": 98, "quantity": 5, "side": "buy"}, "product1")
        self.tester.put_order({"price": 99, "quantity": 8, "side": "buy"}, "product1")
        self.tester.put_order({"price": 98, "quantity": 10, "side": "buy"}, "product1")

        logger.info("Buy and sell orders placed.")

        # Validate order book state
        order_book = self.tester.order_book_request("product1")
        self.assertGreater(len(order_book["Asks"]), 0, "No sell orders found.")
        self.assertGreater(len(order_book["Bids"]), 0, "No buy orders found.")

        # Check Sell Orders Sorting (Lowest Price First)
        ask_prices = [order['Price'] for order in order_book['Asks']]
        self.assertEqual(ask_prices, sorted(ask_prices), "Sell orders are not sorted correctly by price.")

        # Check Buy Orders Sorting (Highest Price First)
        bid_prices = [order['Price'] for order in order_book['Bids']]
        self.assertEqual(bid_prices, sorted(bid_prices, reverse=True), "Buy orders are not sorted correctly by price.")

        logger.info("Price-based sorting validated.")

        # Check Priority (FIFO) for Same-Price Orders
        # Orders with the same price should follow a First-In-First-Out (FIFO) priority
        for side in ['Asks', 'Bids']:
            price_map = {}
            for order in order_book[side]:
                price = order['Price']
                if price not in price_map:
                    price_map[price] = []
                price_map[price].append(order)

            for price, orders in price_map.items():
                if len(orders) > 1:
                    order_times = [order['ID'] for order in orders]
                    self.assertEqual(order_times, sorted(order_times),
                                     f"{side} orders at price {price} are not in FIFO order.")
                    logger.info(f"{side.capitalize()} orders at price {price} follow FIFO correctly.")

        logger.info("Order book management and sorting validation completed.")

    def test_edge_case_handling(self):
        """
        Scenario 3: Edge Case Handling

        Objective: Ensure system handles edge cases gracefully.

        - Attempt invalid orders (e.g., negative price, zero quantity).
        - Attempt to modify non-existent orders.
        - Attempt to delete an order twice.
        """
        logger.info("Starting Scenario 3: Edge Case Handling")

        # Register a user
        self.register_user(5000)

        # Invalid orders
        invalid_orders = [
            {"price": -100, "quantity": 5, "side": "buy"},
            {"price": 100, "quantity": 0, "side": "buy"},
            {"price": float('inf'), "quantity": 1, "side": "sell"}
        ]
        for order in invalid_orders:
            order_id, status = self.trader.put_order(order, "product1")
            self.assertFalse(status, f"Invalid order accepted: {order}")

        # Modify non-existent order
        result = self.trader.modify_order(9999, "product1", new_price=110)
        self.assertFalse(result, "Modified non-existent order.")

        # Delete non-existent order
        result = self.trader.delete_order(9999, "product1")
        self.assertFalse(result, "Deleted non-existent order.")

        # Place valid order and delete twice
        order_id, status = self.trader.put_order({"price": 100, "quantity": 5, "side": "buy"}, "product1")
        self.assertTrue(status, "Failed to place order.")
        result = self.trader.delete_order(order_id, "product1")
        self.assertTrue(result, "Failed to delete order.")
        result = self.trader.delete_order(order_id, "product1")
        self.assertFalse(result, "Deleted the same order twice.")
        logger.info("Edge case handling verified.")

    def test_compute_quantity(self):
        """
        Scenario 4: Compute Quantity Function Test

        Objective: Validate the compute_quantity function under different conditions.

        - Register a new user with a budget of 1000.
        - Test when the order book is empty.
        - Test with valid buy and sell scenarios.
        - Test using different budget ratios.
        - Test edge cases such as zero price or unavailable volume.
        """
        logger.info("Starting Scenario 4: Compute Quantity Function Test")

        # Register a user with a budget of 10000
        self.register_user(10000)

        # Compute quantity when the order book is empty
        quantity = self.trader.compute_quantity("product1", "buy", 100, ratio=0.5)
        self.assertEqual(quantity, 0, "Expected quantity to be 0 when the order book is empty.")
        logger.info("Empty order book test passed.")

        # Populate the order book with sample data
        self.tester.put_order({"price": 100, "quantity": 90, "side": "sell"}, "product1")
        self.tester.put_order({"price": 98, "quantity": 50, "side": "buy"}, "product1")

        # Compute quantity using 50% of the budget (buy scenario)
        quantity = self.trader.compute_quantity("product1", "buy", 100, ratio=0.5)
        self.assertEqual(quantity, 50, "Expected to compute 50 units using 50% of the budget (500/100).")
        logger.info("50% budget test (buy) passed.")

        # Compute quantity using 100% of the budget (buy scenario)
        quantity = self.trader.compute_quantity("product1", "buy", 100, ratio=1.0)
        self.assertEqual(quantity, 90, "Expected to compute 90 units using 100% of the budget, limited by available volume.")
        logger.info("100% budget test (buy) passed.")

        # Compute quantity using invalid price (zero price)
        quantity = self.trader.compute_quantity("product1", "buy", 0, ratio=0.5)
        self.assertEqual(quantity, 0, "Expected quantity to be 0 when price is zero.")
        logger.info("Zero price test passed.")

        # Compute quantity for a sell scenario (no owned volume)
        quantity = self.trader.compute_quantity("product1", "sell", 98, ratio=0.5)
        self.assertEqual(quantity, 0, "Expected quantity to be 0 when no owned volume is available.")
        logger.info("Sell scenario with no volume test passed.")

        logger.info("Compute Quantity function test completed.")

    def test_order_status(self):
        """
        Scenario 5: Order Status Check

        Objective: Validate order status after placing multiple buy and sell orders.

        - Register a new user with a budget of 3000.
        - Place valid, partially filled, fully filled, and invalid orders.
        - Verify order statuses using order_status() for accuracy.
        - Ensure correct handling of invalid and failed orders.
        """
        logger.info("Starting Scenario 5: Order Status Check")

        # 1. Register a new user with a budget of 3000
        self.register_user(3000)

        # Populate the order book with sample data
        self.tester.put_order({"price": 101, "quantity": 10, "side": "sell"}, "product1")
        self.tester.put_order({"price": 100, "quantity": 5, "side": "sell"}, "product1")
        self.tester.put_order({"price": 98, "quantity": 10, "side": "buy"}, "product1")
        self.tester.put_order({"price": 99, "quantity": 5, "side": "buy"}, "product1")
        logger.info("Order book populated with initial data.")

        # 2. Define orders for various scenarios
        orders = [
            {"price": 102, "quantity": 14, "side": "buy"},  # Expected: Fully filled
            {"price": 101, "quantity": 5, "side": "buy"},  # Expected: Partially filled
            {"price": 98, "quantity": 15, "side": "sell"},  # Expected: Fully filled
            {"price": 103, "quantity": 20, "side": "sell"},  # Expected: Failed (Insufficient volume)
            {"price": -10, "quantity": -25, "side": "side"}  # Expected: Invalid order
        ]

        # Expected results for checking
        expected_statuses = [
            "Filled",
            "Partially Filled",
            "Filled",
            "Rejected",
            "Invalid"
        ]

        # 3. Place orders and check order statuses
        for i, order in enumerate(orders):
            logger.info(f"Placing order {i + 1}: {order}")
            order_id, status = self.trader.put_order(order, "product1")

            # Validate order status
            if expected_statuses[i] in ["Rejected", "Invalid"]:
                self.assertFalse(status, f"Expected no order ID for {expected_statuses[i]} order.")
            elif expected_statuses[i] == "Partially Filled":
                self.assertIsNotNone(status, f"Expected valid order ID for {expected_statuses[i]} order.")
            elif expected_statuses[i] == "Filled":
                self.assertIsNone(status, f"Expected no order ID for {expected_statuses[i]} order.")

        logger.info("All order status checks completed successfully.")

    def test_historical_order_books(self):
        """
        Scenario 6: Historical Order Books

        Objective: Validate retrieval of historical order books and ensure accurate storage.

        - Place multiple buy orders at different prices.
        - Retrieve the historical order books for a product (with a lookback of 20 entries).
        - Validate the correct number of order books are returned.
        - Ensure the historical data is consistent with the placed orders.
        """
        logger.info("Starting Scenario 6: Historical Order Books and Cleanup")

        # Register a new user only for clean up purposes
        self.register_user(5)

        # Dynamically generate multiple buy and sell orders
        orders = []
        base_price = 10
        for i in range(1, 25):
            buy_price = base_price + i - 1
            sell_price = buy_price + 1  # Sell price is just 1 higher than the buy price
            quantity = i  # Quantity increases as we go
            # Add a Buy order
            orders.append({"price": buy_price, "quantity": quantity, "side": "buy"})
            # Add a corresponding Sell (Ask) order
            orders.append({"price": sell_price, "quantity": quantity, "side": "sell"})

        logger.info(f"Placing {len(orders)} buy and sell orders for product1.")
        for order in orders:
            order_id, status = self.tester.put_order(order, "product1")
            self.assertIsNotNone(order_id, f"Failed to place order: {order}")
            self.assertTrue(status, f"Order failed for: {order}")
        logger.info("All orders placed successfully.")

        # Retrieve historical order books
        lookback = 20
        historical_order_books = self.trader.historical_order_books("product1", lookback, verbose=False)
        logger.info(f"Retrieved {len(historical_order_books)} historical order books.")

        # Validate the number of order books
        expected_count = min(len(orders) + 1, lookback + 1)  # Including the current state
        self.assertEqual(len(historical_order_books), expected_count,
                         f"Expected {expected_count} order books, got {len(historical_order_books)}")

        # Perform additional data validation
        for i, order_book in enumerate(historical_order_books):
            order_book = json.loads(order_book)
            self.assertTrue(order_book, f"Order book at index {i} is empty.")

            self.assertIn('Asks', order_book, f"Missing 'Asks' in order book at index {i}.")
            self.assertIn('Bids', order_book, f"Missing 'Bids' in order book at index {i}.")

            self.assertIsInstance(order_book['Asks'], list, f"'Asks' should be a list at index {i}.")
            self.assertIsInstance(order_book['Bids'], list, f"'Bids' should be a list at index {i}.")
            logger.info(f"Order book {i} validated successfully.")

        logger.info("Historical order book retrieval and validation completed.")

    def test_delete_dispensable_orders(self):
        """
        Scenario 7: Test deleting dispensable orders.

        Objective: Validate the correct deletion of dispensable orders based on price threshold and history lookback threshold.

        - Register a user with a budget.
        - Place multiple orders with varying prices and timestamps.
        - Test deletion based on price difference threshold.
        - Test deletion based on order age (timestamp) threshold.
        - Ensure non-dispensable orders are not deleted.
        """

        logger.info("Starting Scenario 7: Test deleting dispensable orders.")

        # Register a new user with a budget of 1000
        self.register_user(1000)

        # Place multiple orders with varying prices and timestamps
        orders = [
            {"price": 90, "quantity": 10, "side": "buy"}, # This order should be deleted - price difference > 10
            {"price": 95, "quantity": 15, "side": "buy"},
            {"price": 105, "quantity": 5, "side": "sell"},
            {"price": 100, "quantity": 10, "side": "buy"},
            {"price": 110, "quantity": 20, "side": "sell"}, # This order should be deleted - price difference > 10
        ]

        order_ids = []
        for order in orders:
            order_id, status = self.tester.put_order(order, "product1")
            self.assertIsNotNone(order_id, f"Failed to place order: {order}")
            self.assertTrue(status, f"Order failed for: {order}")
            order_ids.append(order_id)

        logger.info(f"Placed {len(orders)} orders.")

        # Define thresholds for deletion
        price_threshold = 9  # Orders with price difference greater than 10 should be deleted
        history_lookback_threshold = 5  # Orders older than 5 seconds should be deleted

        # Delete orders that are below the price threshold
        logger.info(f"Deleting orders below the price threshold of {price_threshold}.")
        self.tester.delete_dispensable_orders("product1", 100, price_threshold)
        logger.info(f"Dispensable orders deleted based on price threshold.")

        # Check that the correct orders have been deleted based on the criteria
        user_orders = self.tester.list_user_orders("product1")
        self.assertNotIn(order_ids[0], user_orders, f"Order {order_ids[0]} should have been deleted.")
        self.assertNotIn(order_ids[4], user_orders, f"Order {order_ids[4]} should have been deleted.")

        # Wait for 5 seconds to simulate time passage
        logger.info("Waiting for 5 seconds to simulate time passage for time-based deletion.")
        time.sleep(5)  # Wait for 5 seconds before checking for time-based dispensable orders

        # Delete orders that are older than the history lookback threshold
        logger.info(f"Deleting orders older than {history_lookback_threshold} seconds.")
        self.tester.delete_dispensable_orders("product1", 100, price_threshold, history_lookback_threshold)
        logger.info(f"Dispensable orders deleted based on history lookback threshold.")

        # Check that no orders are left
        user_orders = self.tester.list_user_orders("product1")
        self.assertEqual(len(user_orders), 0, "All orders should have been deleted.")
        logger.info("Dispensable orders successfully deleted based on time threshold.")

        logger.info("Test for delete_dispensable_orders with price and time-based thresholds completed successfully.")


if __name__ == '__main__':
    unittest.main()
