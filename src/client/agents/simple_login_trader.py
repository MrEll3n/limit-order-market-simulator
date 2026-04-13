import sys
import requests

sys.path.append('../../..')

from src.client.algorithmic_trader import AlgorithmicTrader


class SimpleLoginTrader(AlgorithmicTrader):
    def __init__(self, name, server, config, product="product1", buy_below=99, sell_above=101):
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
    HOST = "http://127.0.0.1"
    PORT = 8888

    config = requests.get(f"{HOST}:{PORT}/api/config").json()
    config["HOST"] = HOST
    config["PORT"] = PORT

    trader = SimpleLoginTrader("trader", "server", config)

    # Option A: authenticate with email + password (generates a new API key)
    trader.login_via_credentials("your@students.zcu.cz", "your_password")

    # Option B: authenticate with a saved API key (reuses existing key)
    # trader.login_via_apikey("sk-your-api-key")

    trader.start_subscribe()
