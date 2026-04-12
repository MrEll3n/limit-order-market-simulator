import json
import random
import inspect
from locust import task, between, HttpUser, events
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from src.protocols.FIXProtocol import FIXProtocol

# Configuration for the Trader
CONFIG = json.load(open(os.path.join(os.path.dirname(__file__), "../config/server_config.json")))

class TestTrader:
    """
    Client class for communicating with the trading server using Locust's HTTP client.
    - All methods taken from Trader class in src/client/client.py but modified to use Locust's HTTP client.
    - The class is designed to be used with Locust for load testing.
    """
    def __init__(self, client, sender, target, config):
        """
        Initialize the client.
        :param client: Locust's self.client (for tracked HTTP requests)
        :param sender: Sender ID (Client ID)
        :param target: Target ID (Server ID)
        :param config: Server configuration
        """
        self.client = client
        self.PROTOCOL = FIXProtocol(sender, target)
        self.BASE_URL = f"{config['HOST']}:{config['PORT']}"
        self.TRADING_SESSION = config["TRADING_SESSION"]
        self.QUOTE_SESSION = config["QUOTE_SESSION"]

    def parse_response(self, response):
        """
        Parses the server response.
        """
        caller = inspect.stack()[1].function
        try:
            response = response.json()
        except Exception as e:
            print(f"\033[91mError parsing JSON in {caller}: {e}\033[0m")
            return None
        if "error" in response:
            print(f"\033[91mError in {caller}: {response['error']}\033[0m")
            return None
        return response

    def register(self, budget=1000):
        """
        Registers the trader with the server.
        :param budget: Initial budget for the trader.
        """
        data = {"budget": budget, "msg_type": "RegisterRequest"}
        message = self.PROTOCOL.encode(data)
        response = self.client.post(f"/{self.TRADING_SESSION}",
                                    json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})
        response = self.parse_response(response)
        if response is None:
            return None
        response["msg_type"] = "RegisterResponse"
        response_data = self.PROTOCOL.decode(response)
        self.PROTOCOL.set_sender(response_data["user"])

    def put_order(self, order, product):
        """
        Places an order with the server.
        :param order: Order details (side, price, quantity).
        :param product: Product to trade.
        """
        data = {"order": order, "product": product, "msg_type": "NewOrderSingle"}
        message = self.PROTOCOL.encode(data)
        self.client.post(f"/{self.TRADING_SESSION}",
                                    json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})


    def order_book_request(self, product, depth=0):
        """
        Requests the order book for a specific product.
        :param product: Product to fetch the order book for.
        :param depth: Depth of the order book.
        """
        data = {"depth": depth, "product": product, "msg_type": "MarketDataRequest"}
        message = self.PROTOCOL.encode(data)
        self.client.get(f"/{self.QUOTE_SESSION}",
                                   json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})



class TradingServerUser(HttpUser):
    """
    Locust user class for simulating a trading server user.
    - Inherits from HttpUser to use Locust's HTTP client.
    - Defines tasks for placing orders and fetching order books.
    """
    wait_time = between(0.1, 0.5) # Simulate a wait time between tasks

    def on_start(self):
        """
        Initializes the trader when the user starts.
        """
        self.trader = TestTrader(client=self.client, sender="test_trader", target="server", config=CONFIG)
        self.trader.register(budget=1000)

    @task(2)
    def place_order(self):
        """
        Simulates placing a random order.
        """
        product = random.choice(CONFIG["PRODUCTS"])
        side = random.choice(["buy", "sell"])
        price = round(random.uniform(10, 100), 2)
        quantity = random.randint(1, 10)
        order = {"side": side, "price": price, "quantity": quantity}
        self.trader.put_order(order, product)

    @task(1)
    def fetch_order_book(self):
        """
        Simulate fetching the order book.
        """
        product = random.choice(CONFIG["PRODUCTS"])
        self.trader.order_book_request(product)

if __name__ == "__main__":
    @events.test_start.add_listener
    def on_test_start(_, **_kwargs):
        print("Starting Locust test...")

    @events.test_stop.add_listener
    def on_test_stop(_, **_kwargs):
        print("Stopping Locust test...")

    # Run the test with Locust
    os.system("locust -f ./locust_test.py --host=http://127.0.0.1:8888 --headless --users 1000 --spawn-rate 10 --run-time 100s --html=locust_report.html")