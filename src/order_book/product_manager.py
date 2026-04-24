import json

from order_book.matching_engine import FIFOMatchingEngine
from order_book.order_book import OrderBook


class TradingProductManager:
    """
    Manages the order books and matching engines for different trading products.
    """
    def __init__(self, products):
        """
        Initializes the TradingProductManager with a list of products.
        :param products: List of product names.
        """
        self.order_books = {product: OrderBook() for product in products}
        self.historical_order_books = {product: [] for product in products}
        self.matching_engines = {product: FIFOMatchingEngine(self.order_books[product]) for product in products}

    def set_order_book(self, product, order_book):
        """
        Sets the order book for a given product and prepares the matching engine for it.
        :param product: Name of the product.
        :param order_book: The order book object to set.
        """
        if product not in self.order_books:
            raise ValueError(f"Product {product} not found")
        self.order_books[product] = order_book
        self.matching_engines[product] = FIFOMatchingEngine(order_book)

    def get_order_book(self, product, save_history=True, timestamp=None):
        """
        Retrieves the order book for a given product. If save_history is True, it saves the current state of the order book.
        :param product: Name of the product.
        :param save_history: Boolean indicating whether to save the order book to history.
        :param timestamp: Timestamp to set for the order book in case of saving history.
        :return: The order book for the specified product.
        """
        if save_history and timestamp is None:
            raise ValueError("Timestamp must be provided if save_history is True")
        if save_history:
            self.order_books[product].timestamp = self.order_books[product].timestamp + 1
            self.historical_order_books[product].append(self.order_books[product].copy().jsonify_order_book())
        return self.order_books.get(product)

    def get_matching_engine(self, product, timestamp):
        """
        Retrieves the matching engine for a given product and updates the timestamp.
        :param product: Name of the product.
        :param timestamp: Timestamp to set for the order book.
        :return: The matching engine for the specified product.
        """
        self.order_books[product].timestamp = timestamp
        self.historical_order_books[product].append(self.order_books[product].copy().jsonify_order_book())
        return self.matching_engines.get(product)

    def get_historical_order_books(self, product, history_length, since=None):
        """
        Retrieves the historical order books for a given product. If history_length is -1, it returns all historical data.
        :param product: Name of the product.
        :param history_length: Length of history to retrieve. If -1, returns all historical data.
        :param since: Optional Unix timestamp in nanoseconds; only records with Timestamp >= since are returned.
        :return: List of historical order books for the specified product.
        """
        if history_length == -1:
            books = list(self.historical_order_books[product])
        else:
            books = self.historical_order_books[product][-history_length:]
        if since is not None:
            books = [b for b in books if json.loads(b).get("Timestamp", 0) >= since]
        return books