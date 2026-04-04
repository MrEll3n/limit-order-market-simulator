import os
import sys
import requests
import os
from dotenv import load_dotenv

sys.path.append(os.path.join(os.path.dirname(__file__), '../../..'))

from src.client.algorithmic_trader import AlgorithmicTrader


class RangeTrader(AlgorithmicTrader):
    def __init__(self, name, server, config, support_level=99, resistance_level=101):
        """
        Initializes the RangeTrader.
        :param name: Name of the agent
        :param server: Server name
        :param config: Configuration dictionary
        :param support_level: Price threshold below which buy orders are triggered.
        :param resistance_level: Price threshold above which sell orders are triggered.
        """
        super().__init__(name, server, config)
        self.support_level = support_level
        self.resistance_level = resistance_level
        self.prices = {}

    def handle_market_data(self, message):
        """
        Processes incoming market data and updates internal price tracking.
        - Stores the latest bid and ask prices for the given product.
        - Deletes dispensable orders based on mid-price and defined thresholds.
        :param message: Market data message - dictionary with keys "product", "order_book"
        """
        product = message["product"]
        if product not in self.prices:
            self.prices[product] = {"bid": 0, "ask": 0}
        if mid_price := self.mid_price():
            self.prices[product]["bid"] = message["order_book"]["Bids"][0]["Price"]
            self.prices[product]["ask"] = message["order_book"]["Asks"][0]["Price"]
            self.delete_dispensable_orders(product, mid_price, 1, 60)

    def trade(self, message):
        """
        Executes the range trading strategy based on support and resistance levels.
        - Places buy orders when the bid price is below the support level.
        - Places sell orders when the ask price is at or above the resistance level.
        :param message: Market data message - dictionary with keys "product", "order_book"
        """
        product = message["product"]
        bid_price, ask_price = self.prices[product]["bid"], self.prices[product]["ask"]

        # Make trading decisions based on support and resistance levels
        if bid_price < self.support_level:  # Buy
            quantity = self.compute_quantity(product, "buy", bid_price)
            if quantity > 0:
                self.put_order({"side": "buy", "quantity": quantity, "price": bid_price}, product)
        elif ask_price >= self.resistance_level:  # Sell
            quantity = self.compute_quantity(product, "sell", ask_price)
            if quantity > 0:
                self.put_order({"side": "sell", "quantity": quantity, "price": ask_price}, product)


if __name__ == "__main__":
    load_dotenv()
    HOST, PORT = "http://127.0.0.1", 8888
    config = requests.get(f"{HOST}:{PORT}/api/config").json()
    config["HOST"], config["PORT"] = HOST, PORT
    swing_trader = RangeTrader("range_trader", "server", config)
    swing_trader.login_via_credentials("range_trader", os.environ.get("BOT_PASSWORD", "changeme"))
    swing_trader.start_subscribe()
