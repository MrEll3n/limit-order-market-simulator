import requests
import os
from dotenv import load_dotenv
from src.client.algorithmic_trader import AlgorithmicTrader

class Printer(AlgorithmicTrader):
    def __init__(self, name, server, config):
        """
        Initializes the Printer agent.
        :param name: Name of the agent
        :param server: Server name
        :param config: Configuration dictionary
        """
        super().__init__(name, server, config)

    def handle_market_data(self, message):
        """
        Handles incoming market data and prints it to the console.
        :param message: Market data message - dictionary with keys "product", "order_book"
        """
        product = message["product"]
        order_book = message["order_book"]

        # Print the market data
        print(f"Market Data for {product}:")
        self.display_order_book(order_book, product=product, aggregated=False)

    def trade(self, message):
        pass


if __name__ == "__main__":
    load_dotenv()
    HOST, PORT = "http://127.0.0.1", 8888
    config = requests.get(f"{HOST}:{PORT}/api/config").json()
    config["HOST"], config["PORT"] = HOST, PORT
    printer_agent = Printer("test_trader", "server", config)
    printer_agent.login_via_credentials("test_trader", os.environ.get("BOT_PASSWORD", "changeme"))
    printer_agent.start_subscribe()