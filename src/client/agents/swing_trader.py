import pandas as pd
import os
import sys
import requests
import os
from dotenv import load_dotenv
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), '../../..'))

from src.client.algorithmic_trader import AlgorithmicTrader
class SwingTrader(AlgorithmicTrader):
    def __init__(self, name, server, config, lookback=20, bollinger_std=2, confirm_ticks=3, imbalance_threshold=0.2):
        """
        Initializes the SwingTrader with additional indicators.
        :param name: Name of the agent
        :param server: Server name
        :param config: Configuration dictionary
        :param lookback: Number of historical prices to consider
        :param bollinger_std: Standard deviation multiplier for Bollinger Bands (default is 2)
        :param confirm_ticks: Number of ticks to confirm breakout
        :param imbalance_threshold: Threshold for order book imbalance index
        """
        super().__init__(name, server, config)
        self.lookback = lookback
        self.bollinger_std = bollinger_std
        self.confirm_ticks = confirm_ticks
        self.imbalance_threshold = imbalance_threshold
        self.mid_prices = {}

    def handle_market_data(self, message):
        """
        Processes incoming market data and updates the mid-price history for the product.
        - Maintains a rolling window of mid-prices based on the lookback period.
        - Deletes outdated or unnecessary orders based on the current mid-price.
        :param message: Market data message - dictionary with keys "product", "order_book"
        """
        product = message["product"]

        # Initialize data structures for the product if not already
        if product not in self.mid_prices:
            self.mid_prices[product] = []

        if mid_price := self.mid_price():
            self.mid_prices[product].append(mid_price)
            self.mid_prices[product] = self.mid_prices[product][-self.lookback:]
            self.delete_dispensable_orders(product, mid_price, 1, 60)

    def compute_bollinger_bands(self, prices):
        """
        Compute the Bollinger Bands (upper, middle, lower) for the given prices.
        :param prices: List of historical prices
        :return: Upper band, middle band, lower band
        """
        rolling_mean = np.mean(prices)
        rolling_std = np.std(prices)
        upper_band = rolling_mean + self.bollinger_std * rolling_std
        lower_band = rolling_mean - self.bollinger_std * rolling_std
        return upper_band, rolling_mean, lower_band

    def compute_fibonacci_levels(self, high, low):
        """
        Compute Fibonacci retracement levels based on high and low.
        :param high: The recent high price
        :param low: The recent low price
        :return: A dictionary of Fibonacci retracement levels
        """
        diff = high - low
        fib_levels = {
            "23.6%": high - 0.236 * diff,
            "38.2%": high - 0.382 * diff,
            "50%": high - 0.5 * diff,
            "61.8%": high - 0.618 * diff
        }
        return fib_levels

    def trade(self, message):
        """
        Executes the swing trading strategy based on Bollinger Bands, Fibonacci levels, and order book imbalance.
        - Places buy orders when the price is below the lower Bollinger Band and key Fibonacci levels and imbalance index is negative.
        - Places sell orders when the price is above the upper Bollinger Band and key Fibonacci levels and imbalance index is positive.
        :param message: Market data message - dictionary with keys "product", "order_book"
        """
        product = message["product"]
        prices = self.mid_prices[product]

        if len(prices) < self.lookback:
            return  # Not enough data to make a trade

        # Compute Bollinger Bands, Fibonacci Levels, and Imbalance Index
        upper_band, middle_band, lower_band = self.compute_bollinger_bands(prices)
        high = max(prices[-self.lookback:])
        low = min(prices[-self.lookback:])
        fib_levels = self.compute_fibonacci_levels(high, low)

        bids = message["order_book"]["Bids"]
        asks = message["order_book"]["Asks"]
        if not bids or 'Quantity' not in bids[0] or not asks or 'Quantity' not in asks[0]:
            return

        bids_df = pd.DataFrame(bids)
        asks_df = pd.DataFrame(asks)
        imbalance_index = self.imbalance_index(asks_df['Quantity'].values, bids_df['Quantity'].values)

        # Trade logic
        mid_price = prices[-1]
        if mid_price < lower_band and imbalance_index < -self.imbalance_threshold and mid_price < fib_levels["38.2%"]:
            quantity = self.compute_quantity(product, "buy", mid_price)
            if quantity > 0:
                self.put_order({"type": "limit", "side": "buy", "quantity": quantity, "price": mid_price}, product)
        elif mid_price > upper_band and imbalance_index > self.imbalance_threshold  and mid_price > fib_levels["61.8%"]:
            quantity = self.compute_quantity(product, "sell", mid_price)
            if quantity > 0:
                self.put_order({"type": "limit", "side": "sell", "quantity": quantity, "price": mid_price}, product)




if __name__ == "__main__":
    load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))
    HOST, PORT = "http://127.0.0.1", 8888
    config = requests.get(f"{HOST}:{PORT}/api/config").json()
    config["HOST"], config["PORT"] = HOST, PORT
    swing_trader = SwingTrader("swing_trader", "server", config)
    print("[SwingTrader] Authenticating...")
    swing_trader.login_via_credentials("swing_trader", os.environ.get("BOT_PASSWORD", "changeme"))
    print("[SwingTrader] Authenticated successfully.")
    print("[SwingTrader] Starting...")
    swing_trader.start_subscribe()
