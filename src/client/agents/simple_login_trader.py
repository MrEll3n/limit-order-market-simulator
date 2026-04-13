import sys
import os
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../..'))

from src.client.algorithmic_trader import AlgorithmicTrader


class SimpleLoginTrader(AlgorithmicTrader):
    def __init__(self, name, server, config, product="product1", buy_below=105, sell_above=90):
        """
        :param product:    Produkt, se kterým agent obchoduje
        :param buy_below:  Koupí, když je cena pod touto hranicí
        :param sell_above: Prodá, když je cena nad touto hranicí
        """
        super().__init__(name, server, config)
        self.product = product
        self.buy_below = buy_below
        self.sell_above = sell_above

    def handle_market_data(self, message):
        pass

    def trade(self, message):
        product = message["product"]
        if product != self.product:
            return
        mid = self.mid_price()
        if mid is None:
            return

        if mid < self.buy_below:
            quantity = self.compute_quantity(product, "buy", mid)
            if quantity > 0:
                self.put_order({"side": "buy", "quantity": quantity, "price": mid}, product)

        elif mid > self.sell_above:
            quantity = self.compute_quantity(product, "sell", mid)
            if quantity > 0:
                self.put_order({"side": "sell", "quantity": quantity, "price": mid}, product)


if __name__ == "__main__":
    HOST = "https://honicoin.site"

    config = requests.get(f"{HOST}/api/config").json()
    config["HOST"] = HOST

    trader = SimpleLoginTrader("BOTname", "server", config)

    # Option A: authenticate with email + password (generates a new API key)
    trader.login_via_credentials("bot@example.com", "password :D")

    # Option B: authenticate with a saved API key (reuses existing key)
    # trader.login_via_apikey("sk-your-api-key")

    trader.start_subscribe()
