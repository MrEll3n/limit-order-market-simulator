import logging
import random
import time
from abc import ABC
import json
import os
import sys
import requests
from dotenv import load_dotenv

import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), '../../..'))

from src.client.client import AdminTrader

logging.getLogger("urllib3").setLevel(logging.INFO)  # Suppress logging


class SyntheticLiquidityProvider(AdminTrader, ABC):
    def __init__(self, target, config, budget=10000, volume=1000):
        """
        Inicialize Synthetic Liquidity Provider.
        :param target: Name of the server
        :param config: Configuration dictionary
        :param budget: Total budget to allocate for generating liquidity
        :param volume: Total volume to allocate for generating liquidity
        """
        super().__init__("liquidity_generator", target, config)
        load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))
        print("[LiquidityGenerator] Authenticating...")
        if not self.login_via_credentials(
            email=os.environ.get("LIQUIDITY_GENERATOR_EMAIL", "liquidity_generator"),
            password=os.environ.get("LIQUIDITY_GENERATOR_PASSWORD", "changeme"),
        ):
            print("[LiquidityGenerator] Authentication failed. Exiting.")
            return
        print("[LiquidityGenerator] Authenticated successfully.")
        self.initialize_liquidity_engine(budget, volume)
        self.products = config["PRODUCTS"]
        print(f"[LiquidityGenerator] Initialized. Products: {self.products}, Budget: {budget}, Volume: {volume}")

    def receive_market_data(self, data):
        pass

    def generate_liquidity(self):
        """
        Generate synthetic liquidity by placing random orders.
        - Orders are placed randomly on the bid or ask side with random price and quantity.
        - Side is selected based on the volume of Bids and Asks (weighted random choice).
        """
        while True:
            try:
                time.sleep(random.randint(1, 5))  # Sleep for 1-5 seconds
                product = random.choice(self.products)
                order_book = self.order_book_request(product, depth=10)
                if order_book is None:
                    continue
                bid_volume = sum([order["Quantity"] for order in order_book["Bids"]])
                ask_volume = sum([order["Quantity"] for order in order_book["Asks"]])
                if bid_volume == 0 and ask_volume == 0:
                    continue  # Skip this iteration if both Bids and Asks are empty
                side = np.random.choice(["sell", "buy"], p=[bid_volume / (bid_volume + ask_volume),
                                                            ask_volume / (bid_volume + ask_volume)])
                # randomly select a price
                if side == "buy":
                    if order_book["Bids"]:
                        price = order_book["Bids"][0]["Price"]
                    elif order_book["Asks"]:
                        price = order_book["Asks"][0]["Price"]
                    else:
                        continue  # Skip this iteration if both Bids and Asks are empty
                else:
                    if order_book["Asks"]:
                        price = order_book["Asks"][0]["Price"]
                    elif order_book["Bids"]:
                        price = order_book["Bids"][0]["Price"]
                    else:
                        continue  # Skip this iteration if both Bids and Asks are empty
                self.delete_dispensable_orders(product, price, 5, 60)
                price = price + random.uniform(-0.5, 0.5)  # Add some noise to the price
                quantity = self.compute_quantity(product, side, price)
                if side == "sell":
                    bid_volume = sum([order["Quantity"] for order in order_book["Bids"][:5]])
                    counter_side_volume = max(1, bid_volume // 4)
                    quantity = min(counter_side_volume, quantity)  # Limit maximum quantity
                if quantity > 0:
                    self.put_order({"side": side, "quantity": quantity, "price": price}, product)
                    logging.info(f"Synthetic liquidity added: {side} order at {price} for {quantity} {product}")
            except Exception as e:
                logging.error(f"Error in generating liquidity: {e}")
                continue


if __name__ == "__main__":
    load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))
    HOST = os.environ.get("HOST", "http://127.0.0.1")
    PORT = int(os.environ.get("PORT", 8888))
    config = requests.get(f"{HOST}:{PORT}/api/config").json()
    config["HOST"] = HOST
    config["PORT"] = PORT
    liquidity_generator = SyntheticLiquidityProvider("server", config)
    liquidity_generator.generate_liquidity()
