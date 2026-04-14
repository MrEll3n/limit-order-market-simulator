import logging
import time
from abc import ABC
import json
from statistics import stdev
import numpy as np
import os
import sys
import requests
from dotenv import load_dotenv
sys.path.append(os.path.join(os.path.dirname(__file__), '../../..'))
from src.client.client import AdminTrader

logging.getLogger("urllib3").setLevel(logging.WARNING)  # suppress logging

class MarketMaker(AdminTrader, ABC):
    def __init__(self, target, config, bid_ask_spread=0.5, window=10, volatility_multiplier=0.5, initial_emission=500,
                 starting_price=100, initial_num_orders=10, budget=50000, volume=None):
        """
        Initialize a market maker.
        :param target: Name of the server
        :param config: Configuration dictionary
        :param bid_ask_spread: Fixed bid-ask spread
        :param window: Number of previous mid-prices to consider for volatility calculation
        - Shorter windows (e.g., 5) → Faster response but more noise.
        - Longer windows (e.g., 20-50) → Smoother but slower response.
        :param volatility_multiplier: Determines how much the spread widens when volatility is high
        - Higher values (e.g., 0.7 - 1.0) → More conservative, reducing risk but leading to fewer trades.
        - Lower values (e.g., 0.2 - 0.4) → Keeps the spread tight, increasing trade frequency but raising risk.
        :param initial_emission: Initial volume of liquidity to emit
        - Available types: fixed number for all products same or dictionary with product specific values
        :param starting_price: Starting value for the mid-price
        - Available types: fixed number for all products same or dictionary with product specific values
        :param initial_num_orders: Initial number of orders to emit
        - Available types: fixed number for all products same or dictionary with product specific values
        :param budget: Total budget to allocate for market making (initialization not included)
        :param volume: Total volume to allocate for market making (initialization not included)
        - Available types: fixed number for all products same or dictionary with product specific values
        """
        super().__init__("market_maker", target, config)
        self.bid_ask_spread = bid_ask_spread
        self.window = window
        self.volatility_multiplier = volatility_multiplier
        self.mid_prices = {}
        self.products = config["PRODUCTS"]
        self.initial_emission = {product: initial_emission for product in self.products} \
            if isinstance(initial_emission, int) else initial_emission
        product_settings = config.get("PRODUCT_SETTINGS", {})
        self.starting_price = {
            product: product_settings.get(product, {}).get("INITIAL_PRICE", starting_price)
            for product in self.products
        }
        self.initial_num_orders = {product: initial_num_orders for product in self.products} \
            if isinstance(initial_num_orders, int) else initial_num_orders

        load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))
        print("[MarketMaker] Authenticating...")
        if not self.login_via_credentials(
            email=os.environ.get("MARKET_MAKER_EMAIL", "market_maker"),
            password=os.environ.get("MARKET_MAKER_PASSWORD", "changeme"),
        ):
            print("[MarketMaker] Authentication failed. Exiting.")
            return
        print("[MarketMaker] Authenticated successfully.")
        self.initialize_liquidity_engine(budget, volume)
        print(f"[MarketMaker] Initialized. Products: {self.products}, Budget: {budget}, Volume: {volume}")

    def receive_market_data(self, data):
        pass

    def calculate_dynamic_spread(self, product):
        """
        Calculate the dynamic spread based on the volatility of the mid-price.
        :param product: Product name
        :return: Dynamic spread
        """
        if product not in self.mid_prices:
            return self.bid_ask_spread
        if len(self.mid_prices[product]) < self.window:
            return self.bid_ask_spread
        volatility = stdev(self.mid_prices[product][-self.window:])
        return max(self.bid_ask_spread, volatility * self.volatility_multiplier)

    def get_historical_mid_prices(self, product):
        """
        Get historical mid-prices for a product.
        :param product: Product name
        :return: Bids and Asks from historical order books
        """
        historical_order_books = self.historical_order_books(product, self.window, verbose=False)
        self.mid_prices[product] = []
        bids, asks = None, None
        for i, order_book in enumerate(historical_order_books):
            order_book_dict = json.loads(order_book)
            bids, asks = order_book_dict["Bids"], order_book_dict["Asks"]
            if bids or asks:
                price = (bids[0]["Price"] if bids else asks[0]["Price"]) \
                    if not bids or not asks else (bids[0]["Price"] + asks[0]["Price"]) / 2
                self.mid_prices[product].append(price)
        return bids, asks

    def generate_market_data(self):
        """
        Continuously generates market data by placing synthetic orders based on historical mid-prices.
        - Retrieves historical mid-prices to calculate dynamic spreads for each product.
        - Places buy or sell orders depending on the availability of bids and asks.
        - Ensures orders are placed with appropriate quantities and prices derived from market conditions.
        """
        while True:
            try:
                time.sleep(1)  # Sleep for 1 second
                for product in self.products:
                    bids, asks = self.get_historical_mid_prices(product)
                    dynamic_spread = self.calculate_dynamic_spread(product)
                    side = None
                    price = None

                    if not self.mid_prices.get(product):  # Ensure price history is available
                        continue

                    if not bids:
                        side = "buy"
                        price = self.mid_prices[product][-1] - dynamic_spread
                    if not asks:
                        side = "sell"
                        price = self.mid_prices[product][-1] + dynamic_spread
                    if side:
                        quantity = self.compute_quantity(product, side, price)
                        if quantity > 0:
                            self.put_order({"side": side, "quantity": quantity, "price": price}, product)
                            logging.info(f"Synthetic liquidity added: {side} order at {price} for {quantity} {product}")
            except Exception as e:
                logging.error(f"Error in generating market data: {e}")
                continue

    def initialize_market(self, scale=0.1):
        """
        Adds initial liquidity to the market by placing a set number of buy and sell orders.
        - Bid and ask prices are generated using an exponential distribution around the starting price.
        - Quantities for bids and asks are weighted to ensure a balanced distribution.
        :param scale: Scale factor for the exponential distribution, controlling price and quantity spread.
        """
        for product in self.products:
            num_orders = self.initial_num_orders[product]
            bid_prices = np.sort(self.starting_price[product] - np.random.exponential(scale * num_orders, num_orders))
            ask_prices = np.sort(self.starting_price[product] + np.random.exponential(scale * num_orders, num_orders))[::-1]

            bid_weights = np.sort(np.random.exponential(scale * num_orders, num_orders))[::-1]
            ask_weights = np.sort(np.random.exponential(scale * num_orders, num_orders))[::-1]
            bid_weights /= bid_weights.sum()
            ask_weights /= ask_weights.sum()

            bid_quantities = (self.initial_emission[product]//2 * bid_weights).astype(int)
            ask_quantities = (self.initial_emission[product]//2 * ask_weights).astype(int)

            for side, prices, quantities in [("buy", bid_prices, bid_quantities),
                                            ("sell", ask_prices, ask_quantities)]:
                for i, price in enumerate(prices):
                    quantity = max(1, quantities[i])
                    self.put_order({"side": side, "quantity": quantity, "price": price}, product)
                    print(f"Initial liquidity added: {side} order at {price} for {quantity} {product}")


if __name__ == "__main__":
    load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))
    HOST = os.environ.get("HOST", "http://127.0.0.1")
    PORT = int(os.environ.get("PORT", 8888))
    config = requests.get(f"{HOST}:{PORT}/api/config").json()
    config["HOST"] = HOST
    config["PORT"] = PORT
    market_maker = MarketMaker("server", config, volume={"product1": 1000, "product2": 200},
                               initial_emission={"product1": 500, "product2": 400})
    market_maker.initialize_market()
    market_maker.generate_market_data()
