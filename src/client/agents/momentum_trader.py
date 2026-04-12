import pandas as pd
import requests
import os
from dotenv import load_dotenv
import numpy as np
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '../../..'))

from src.client.algorithmic_trader import AlgorithmicTrader

class MomentumTrader(AlgorithmicTrader):
    def __init__(self, name, server, config, metric, lookback=20, volatility_threshold=0.02):
        """
        Initializes the MomentumTrader.
        :param name: Name of the agent
        :param server: Server name
        :param config: Configuration dictionary
        :param metric: Metric to use for momentum calculation: "percentage_change", "RSI", "SMA", "EMA"
        :param lookback: Number of historical prices to consider - base your choice on the selected metric
        :param volatility_threshold: Maximum allowable volatility to execute trades.
        """
        super().__init__(name, server, config)
        self.metric = self.select_metric(metric)
        self.lookback = lookback
        self.volatility_threshold = volatility_threshold
        self.mid_prices = {}

    def select_metric(self, metric):
        """
        Select the metric function based on the provided metric name.
        :param metric: Metric name
        :return: Corresponding metric function or default to percentage change
        """
        metrics = {
            "percentage_change": self.compute_percentage_change,
            "RSI": self.compute_RSI,
            "SMA": self.compute_SMA,
            "EMA": self.compute_EMA
        }
        return metrics.get(metric, self.compute_percentage_change)  # Default to percentage change

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

    @staticmethod
    def compute_percentage_change(prices):
        """
        Compute the percentage change between the first and last prices.
        :param prices: List of historical prices
        :return: Signal value based on percentage change - positive for increase, negative for decrease
        """
        return (prices[-1] - prices[0]) / prices[0] * 100 # Percentage change

    @staticmethod
    def compute_RSI(prices):
        """
        Compute the Relative Strength Index (RSI) based on historical prices.
         - RSI > 70 indicates overbought, RSI < 30 indicates oversold.
        :param prices: List of historical prices
        :return: Signal value based on RSI - positive for overbought, negative for oversold
        """
        deltas = np.diff(prices)
        gain = np.mean(deltas[deltas > 0]) if any(deltas > 0) else 0
        loss = np.mean(-deltas[deltas < 0]) if any(deltas < 0) else 1  # Prevent division by zero
        rs = gain / loss if loss != 0 else float('inf')
        rsi = 100 - (100 / (1 + rs))
        return -1 if rsi > 70 else 1 if rsi < 30 else 0  # Overbought, oversold, neutral

    @staticmethod
    def compute_SMA(prices):
        """
        Compute the Simple Moving Average (SMA) based on historical prices.
        :param prices: List of historical prices
        :return: Signal value based on SMA - positive for price above SMA, negative for price below SMA
        """
        sma = np.mean(prices)
        return 1 if prices[-1] > sma else -1  # Price above/below SMA

    @staticmethod
    def compute_EMA(prices):
        """
        Compute the Exponential Moving Average (EMA) based on historical prices.
        :param prices: List of historical prices
        :return: Signal value based on EMA - positive for price above EMA, negative for price below EMA
        """
        alpha = 2 / (len(prices) + 1)
        ema =  pd.Series(prices).ewm(alpha=alpha, adjust=False).mean().iloc[-1]
        return 1 if prices[-1] > ema else -1  # Price above/below EMA


    def trade(self, message):
        """
        Executes trades based on the selected momentum metric and market conditions.
        - Skips trading if there is insufficient historical data or if volatility exceeds the threshold.
        - Places buy orders for positive momentum and sell orders for negative momentum.
        :param message: Market data message - dictionary with keys "product", "order_book"
        """
        product = message["product"]
        if len(self.mid_prices[product]) < self.lookback:
            return # Skip trading if not enough historical data

        momentum = self.metric(self.mid_prices[product])

        # Calculate volatility
        volatility = np.std(self.mid_prices[product][-self.lookback:])

        if volatility > self.volatility_threshold:
            return  # Skip trading if volatility is too high

        # Trade based on momentum
        if momentum > 0:
            quantity = self.compute_quantity(product, "buy", self.mid_prices[product][-1])
            if quantity > 0:
                self.put_order({"side": "buy", "quantity": quantity, "price": self.mid_prices[product][-1]}, product)
        elif momentum < 0:
            quantity = self.compute_quantity(product, "sell", self.mid_prices[product][-1])
            if quantity > 0:
                self.put_order({"side": "sell", "quantity": quantity, "price": self.mid_prices[product][-1]}, product)


if __name__ == "__main__":
    load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))
    HOST, PORT = "http://127.0.0.1", 8888
    config = requests.get(f"{HOST}:{PORT}/api/config").json()
    config["HOST"], config["PORT"] = HOST, PORT
    momentum_trader = MomentumTrader("momentum_trader_percentage_change", "server", config, "percentage_change")
    print("[MomentumTrader] Authenticating...")
    momentum_trader.login_via_credentials("momentum_trader_percentage_change", os.environ.get("BOT_PASSWORD", "changeme"))
    print("[MomentumTrader] Authenticated successfully.")
    print("[MomentumTrader] Starting...")
    momentum_trader.start_subscribe()
