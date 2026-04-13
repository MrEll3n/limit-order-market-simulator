import sys
import os
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from src.client.algorithmic_trader import AlgorithmicTrader


class YourTraderName(AlgorithmicTrader):
    def __init__(self, name, server, config):  # Feel free to add any parameters you need
        super().__init__(name, server, config)

    def handle_market_data(self, message):
        """
        Called automatically whenever new market data arrives.

        :param message: A dictionary containing market info, with keys:
                        - "product": Name of the traded asset
                        - "order_book": The current order book (bids/asks)

        This method is useful for:
        - Analyzing live market conditions
        - Tracking price trends
        - Updating internal strategy state

        You *must* implement this method.
        """
        product = message["product"]
        order_book = message["order_book"]

        # Display raw order book data in the terminal for debugging/monitoring
        print(f"Market Data for {product}:")
        self.display_order_book(order_book, product=product, aggregated=False)

        # Feel free to store/compute any data you need for your strategy
        # Some indicators are already available in the AlgorithmicTrader class for example mid_price

        # You can also use the following method to delete orders that are no longer relevant
        # self.delete_dispensable_orders() # Read method description in Trader class for more details

    def trade(self, message):
        """
        Called periodically to make trading decisions.

        :param message: A dictionary containing market info, with keys:
                        - "product": Name of the traded asset
                        - "order_book": The current order book (bids/asks)

        Your trading logic goes here — you can:
        - Analyze market state
        - Use indicators or signals
        - Place, modify, or cancel orders

        Useful built-in methods:
        - self.compute_quantity(): Helps determine safe trade sizes
        - self.put_order(): Places a new limit order (buy/sell)
        - self.delete_order(): Cancels an existing order
        - self.modify_order(): Changes an existing order
        - you can find more in the Trader class (src/client/client.py)
        """
        pass


if __name__ == "__main__":
    HOST = "http://127.0.0.1"
    PORT = 8888

    config = requests.get(f"{HOST}:{PORT}/api/config").json()
    config["HOST"] = HOST
    config["PORT"] = PORT

    your_trader = YourTraderName("trader", "server", config)

    # Option A: authenticate with email + password (generates a new API key)
    your_trader.login_via_credentials("your@students.zcu.cz", "your_password")

    # Option B: authenticate with a saved API key (reuses existing key)
    # your_trader.login_via_apikey("sk-your-api-key")

    your_trader.start_subscribe()
