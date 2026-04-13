import json
import asyncio
import inspect
import sys
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
from abc import ABC, abstractmethod
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.websocket import websocket_connect
from src.protocols.FIXProtocol import FIXProtocol

session = requests.Session()
retry = Retry(connect=10, backoff_factor=0.5)
adapter = HTTPAdapter(max_retries=retry)

session.mount('http://', adapter)
session.mount('https://', adapter)

class Subscriber(ABC):
    """
    Subscriber class for subscribing to the trading server for updates on orders and trades.
    """
    def __init__(self, url, protocol, timeout=1):
        """
        Initialize the subscriber.
        :param url: URL to connect to
        :param protocol: Protocol object for encoding and decoding messages
        :param timeout: Timeout in seconds for maintaining the connection (heartbeats)
        """
        self.url = url
        self.protocol = protocol
        self.loop = IOLoop.instance()
        self.ws = None
        asyncio.ensure_future(self.connect())
        timeout = timeout * 1000  # to seconds
        PeriodicCallback(self.maintain_connection, timeout).start()

    def start_subscribe(self):
        """
        Start the subscription loop.
        """
        self.loop.start()

    async def connect(self):
        """
        Connect to the server via WebSocket.
        """
        try:
            self.ws = await websocket_connect(self.url)
        except Exception as e:
            print(f"Connection error: {e}")
        else:
            print("Subscription successful")
            await self.subscribe()

    async def maintain_connection(self):
        """
        Send a heartbeat message to the server to maintain the connection.
        """
        if self.ws is None:
            await self.connect()
        else:
            await self.ws.write_message("Heartbeat")

    async def subscribe(self):
        """
        Subscribe to the server for updates.
        """
        while True: # Keep the connection open
            msg = await self.ws.read_message()
            if msg is None:
                print("Connection closed")
                self.ws = None
                break
            if msg == ">Heartbeat":
                continue
            try:
                data = json.loads(msg)
                data["msg_type"] = "MarketDataSnapshot"
                data = self.protocol.decode(data)
                self.receive_market_data(data)
            except json.JSONDecodeError:
                print(f"Error decoding message: {msg}")
                continue
            # except Exception as e:
            #     print(f"Error fetching data: {e}")
            #     continue

    @abstractmethod
    def receive_market_data(self, data):
        """
        Handle market data received from the server.
        :param data: JSON with market data
        """
        pass

    def __del__(self):
        """
        Destructor - close the WebSocket connection.
        """
        if self.ws is not None:
            self.ws.close()



class Trader (Subscriber, ABC):
    """
    Client class for communicating with the trading server.
    """

    def __init__(self, sender, target, config):
        """
        Initialize the client.
        :param sender: Sender ID (Client ID)
        :param target: Target ID (Server ID)
        :param config: Configuration dictionary with server details, e.g. HOST, PORT, TRADING_SESSION, QUOTE_SESSION
        """
        self.PROTOCOL = FIXProtocol(sender, target)
        host = config['HOST']
        port = config.get('PORT')
        ws_scheme = "wss" if host.startswith("https") else "ws"
        host_stripped = host.replace('https://', '').replace('http://', '')
        if port:
            ws_url = f"{ws_scheme}://{host_stripped}:{port}/websocket"
            self.BASE_URL = f"{host}:{port}"
        else:
            ws_url = f"{ws_scheme}://{host_stripped}/websocket"
            self.BASE_URL = host
        super().__init__(ws_url, self.PROTOCOL)
        self.TRADING_SESSION = config["TRADING_SESSION"]
        self.QUOTE_SESSION = config["QUOTE_SESSION"]

    @staticmethod
    def parse_response(response):
        """
        Parse the response from the server.
        :param response: Response from the server
        :return: JSON with response data if successful, None otherwise
        """
        caller = inspect.stack()[1].function
        if not response.content:
            print(f"\033[91mError in {caller}: empty response (status {response.status_code})\033[0m")
            return None
        try:
            response = response.json()
        except Exception:
            print(f"\033[91mError in {caller}: invalid JSON response (status {response.status_code})\033[0m")
            return None
        if "error" in response:
            print(f"\033[91mError in {caller}: {response['error']}\033[0m")  # Print in red
            return None
        return response

    def login_via_UUID(self, uuid):
        """
        Login to the server using a UUID.
        :param uuid: UUID from the website
        """
        self.PROTOCOL.set_sender(uuid)
        return True

    def login_via_apikey(self, api_key: str):
        """
        Authenticate all FIX requests using an API key.
        The key is sent as X-API-Key header with every request.
        :param api_key: API key generated via the web frontend
        """
        session.headers.update({"X-API-Key": api_key})

    def login_via_credentials(self, email: str, password: str) -> str | None:
        """
        Authenticate using email and password via the REST API.
        Automatically generates an API key and uses it for FIX requests.
        :param email: User email
        :param password: User password
        :return: API key if successful, None otherwise
        """
        # Step 1: Login via REST to get JWT
        response = session.post(
            f"{self.BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
        )
        data = response.json()
        if not response.ok:
            print(f"\033[91mLogin failed: {data.get('error', 'Unknown error')}\033[0m")
            return None

        access_token = data["accessToken"]
        user_id = data["userId"]

        # Step 2: Generate an API key
        response = session.post(
            f"{self.BASE_URL}/api/account/apikey",
            json={"name": self.PROTOCOL.SENDER.replace("49=", "")},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        data = response.json()
        if not response.ok:
            print(f"\033[91mAPI key generation failed: {data.get('error', 'Unknown error')}\033[0m")
            return None

        api_key = data["key"]
        self.login_via_apikey(api_key)
        self.PROTOCOL.set_sender(user_id)
        return api_key

    def register(self, budget=1000):
        """
        Register a new user with the server.
        :param budget: Initial budget if not set by server
        :return: Unique user ID if successful, None otherwise
        """
        data = {"budget": budget, "msg_type": "RegisterRequest"}
        message = self.PROTOCOL.encode(data)
        response = session.post(f"{self.BASE_URL}/{self.TRADING_SESSION}",
                                 json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})
        response = self.parse_response(response)
        if response is None:
            return None
        response["msg_type"] = "RegisterResponse"
        response_data = self.PROTOCOL.decode(response)
        print(f"User registered with ID: {response_data['user']}")
        # Change the user ID to the unique user ID returned by the server
        self.PROTOCOL.set_sender(response_data["user"])
        return response_data["user"]

    def order_stats(self, ID, product):
        """
        Request order status from the server.
        :param ID: Order ID
        :param product: Product name
        :return: JSON with order details (id, timestamp, user, side, quantity, price) if found, None otherwise
        """
        data = {"ID": ID, "product": product, "msg_type": "OrderStatusRequest"}
        message = self.PROTOCOL.encode(data)

        response = session.get(f"{self.BASE_URL}/{self.QUOTE_SESSION}",
                                json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})
        response = self.parse_response(response)
        if response is None:
            return None
        response["msg_type"] = "OrderStatus"
        order = self.PROTOCOL.decode(response)
        return order

    def put_order(self, order, product):
        """
        Send a new order request to the server.
        :param order: Dictionary containing order details
        :param product: Product name
        :return: Order ID and status (True if successful, None if fully filled, False otherwise)
        """
        data = {"order": order, "product": product, "msg_type": "NewOrderSingle"}
        message = self.PROTOCOL.encode(data)

        response = session.post(f"{self.BASE_URL}/{self.TRADING_SESSION}",
                                 json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})
        response = self.parse_response(response)
        if response is None:
            return None, False
        response["msg_type"] = "ExecutionReport"
        response_data = self.PROTOCOL.decode(response)
        if response_data.get("status") is False:
            print("\033[91mError: Order put failed. Please check the order details and remaining balance.\033[0m")
            return None, False

        return response_data["order_id"], response_data["status"]

    def delete_order(self, ID, product):
        """
        Send an order cancel request to the server.
        :param ID: Order ID
        :param product: Product name
        :return: True if successful, False otherwise
        """
        data = {"ID": ID, "product": product, "msg_type": "OrderCancelRequest"}
        message = self.PROTOCOL.encode(data)

        response = session.post(f"{self.BASE_URL}/{self.TRADING_SESSION}",
                                 json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})
        response = self.parse_response(response)
        if response is None:
            return None
        response["msg_type"] = "ExecutionReportCancel"
        response_data = self.PROTOCOL.decode(response)
        return response_data["status"]

    def modify_order_qty(self, ID, quantity, product):
        """
        Modify order quantity - only decrease is allowed.
        :param ID: Order ID
        :param quantity: New quantity
        :param product: Product name
        :return: True if successful, False otherwise
        """
        data = {"ID": ID, "quantity": quantity, "product": product, "msg_type": "OrderModifyRequestQty"}
        message = self.PROTOCOL.encode(data)
        response = session.post(f"{self.BASE_URL}/{self.TRADING_SESSION}",
                                 json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})
        response = self.parse_response(response)
        if response is None:
            return None
        response["msg_type"] = "ExecutionReportModify"
        response_data = self.PROTOCOL.decode(response)
        return response_data["status"]

    def modify_order(self, ID, product, new_price=None, new_quantity=None):
        """
        Modify an existing order - price and/or quantity.
        :param ID: Order ID
        :param product: Product name
        :param new_price: New price (or None)
        :param new_quantity: New quantity (or None)
        :return: Order ID and status (True if successful, None if fully filled, False otherwise)
        """
        order = self.order_stats(ID, product)
        if order is None:
            print(f"\033[91mError: Order {ID} not found.\033[0m")
            return None
        self.delete_order(ID, product)
        if new_price is not None:
            order['price'] = new_price
        if new_quantity is not None:
            order['quantity'] = new_quantity
        return self.put_order(order, product)

    def order_book_request(self, product, depth=0):
        """
        Returns the order book for a specific product from the server.
        :param product: Product name
        :param depth: Market depth (0 = full book)
        :return: JSON with order book data
        """
        data = {"depth": depth, "product": product, "msg_type": "MarketDataRequest"}
        message = self.PROTOCOL.encode(data)
        response = session.get(f"{self.BASE_URL}/{self.QUOTE_SESSION}",
                                json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})
        response = self.parse_response(response)
        if response is None:
            return None
        order_book_data = response
        order_book_data["msg_type"] = "MarketDataSnapshot"
        order_book_data = self.PROTOCOL.decode(order_book_data)["order_book"]

        return order_book_data

    def list_user_orders(self, product):
        """
        Returns a list of orders for a specific user.
        :param product: Product name
        :return: JSON with order data
        """
        data = {"product": product, "msg_type": "UserOrderStatusRequest"}
        message = self.PROTOCOL.encode(data)
        response = session.get(f"{self.BASE_URL}/{self.QUOTE_SESSION}",
                                json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})
        response = self.parse_response(response)
        if response is None:
            return None
        response["msg_type"] = "UserOrderStatus"
        data = self.PROTOCOL.decode(response)
        data = data["user_orders"]
        return data

    def user_balance(self, product, verbose=True):
        """
        Returns the user's balance for a specific product.
        {'current_balance': {'balance': 0, 'volume': 0, 'post_sell_volume': 0}, 'budget': 10000, 'post_buy_budget': 10000}
        :param product: Product name
        :param verbose: If True, print the user's balance
        :return: Dictionary with user balance data with keys 'current_balance', 'budget', 'post_buy_budget'
        - current_balance['balance']: Current balance - flat income
        - current_balance['volume']: Current owned volume
        - current_balance['post_sell_volume']: Current owned volume if all sell orders are executed
        - budget: Initial budget - fees
        - post_buy_budget: Budget after all buy orders are executed
        """
        data = {"product": product, "msg_type": "UserBalanceRequest"}
        message = self.PROTOCOL.encode(data)
        response = session.get(f"{self.BASE_URL}/{self.QUOTE_SESSION}",
                                json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})
        response = self.parse_response(response)
        if response is None:
            return None
        response["msg_type"] = "UserBalance"
        data = self.PROTOCOL.decode(response)
        if verbose:
            print(f"User balance for {product}: {data['user_balance']}")
        return data["user_balance"]

    def historical_order_books(self, product, history_length, verbose=True):
        """
        Returns the historical order books for a specific product.
        :param product: Product name
        :param history_length: Number of historical order books to return + 1 (current order book)
        :param verbose: If True, print the historical order books
        :return: historical order books
        """
        data = {"product": product, "history_len": history_length, "msg_type": "CaptureReportRequest"}
        message = self.PROTOCOL.encode(data)
        response = session.get(f"{self.BASE_URL}/{self.QUOTE_SESSION}",
                                json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})
        response = self.parse_response(response)
        if response is None:
            return []
        response["msg_type"] = "CaptureReport"
        data = self.PROTOCOL.decode(response)
        if verbose:
            print(f"Historical order books for {product}:")
            for i, order_book in enumerate(data["history"]):
                order_book_dict = json.loads(order_book)  # Parse the order_book string to a dictionary
                print(f"Order book {i}:, timestamp: {order_book_dict['Timestamp']}")
                print("=====================================")
                self.display_order_book(order_book_dict, product=product)
                print()
        return data["history"]

    @staticmethod
    def display_order_book(order_book_data, aggregated=False, product=None):
        """
        Display the order book in a human-readable format. For debugging purposes.
        :param order_book_data: JSON with order book data
        :param aggregated: If True, display aggregated order book
        :param product: Product name
        """
        if product is not None:
            print(f"Order book for {product}:")
            print("=====================================")
        if order_book_data is None:
            print(f"\033[91mError: Order book for {product} not found.\033[0m")
            return

        bids_df = pd.DataFrame(order_book_data['Bids'])
        asks_df = pd.DataFrame(order_book_data['Asks'])

        if bids_df.empty and asks_df.empty:
            print("Order book is empty.")
            return

        if aggregated:
            print("Aggregated order book:")

            # Aggregate the order book
            if not bids_df.empty:
                bids_df = bids_df.groupby('Price', as_index=False).agg(
                    {'Quantity': 'sum', 'ID': 'count', 'User': 'first'})
            if not asks_df.empty:
                asks_df = asks_df.groupby('Price', as_index=False).agg(
                    {'Quantity': 'sum', 'ID': 'count', 'User': 'first'})

        # Concatenate bids and asks DataFrames side by side
        order_book_df = pd.concat([bids_df, asks_df], axis=1, keys=['Bids', 'Asks'])

        # Print the concatenated DataFrame
        print(order_book_df.fillna('').to_string(index=False))

    def compute_quantity(self, product, side, price, ratio=0.1):
        """
        Compute the quantity based on the budget and price.
        :param product: Product name
        :param side: Side (buy or sell)
        :param price: Price
        :param ratio: Ratio of the budget to use
        :return: Optimal quantity to trade
        """
        user_balance = self.user_balance(product, verbose=False)
        order_book_data = self.order_book_request(product)
        if user_balance is None:
            print("\033[91mError: User balance not found.\033[0m")
            return 0
        if order_book_data is None:
            print("\033[91mError: Order book not found.\033[0m")
            return 0

        quantity = 0
        owned_volume = sys.maxsize
        post_buy_budget = sys.maxsize
        if side == "sell": # If selling, use the current owned volume
            owned_volume = user_balance["current_balance"]["post_sell_volume"]
            available_volume = pd.DataFrame(order_book_data['Bids'])
        else: # If buying, use the post-buy budget
            post_buy_budget = user_balance["post_buy_budget"] * ratio
            available_volume = pd.DataFrame(order_book_data['Asks'])

        if not available_volume.empty: # Aggregated order book
            available_volume = available_volume.groupby('Price', as_index=False).agg(
                {'Quantity': 'sum', 'ID': 'count', 'User': 'first'})
            available_volume = sum(available_volume['Quantity'][:min(10, len(available_volume))])
        else:
            available_volume = 0
        if price != 0:
            quantity = min(available_volume, int(post_buy_budget / price), owned_volume)
        return quantity


    def delete_dispensable_orders(self, product, price, price_threshold,  history_lookback_threshold=60):
        """
        Delete dispensable orders - orders with a price difference greater than the threshold or older than the lookback threshold.
        :param product: Product name
        :param price: Current traded price
        :param price_threshold: Threshold for price difference - if the price difference is greater than this, cancel the order
        :param history_lookback_threshold: Maximum age of orders in seconds. Orders older than this threshold will be considered for cancellation.
        :return: List of dispensable order IDs
        """
        user_orders = self.list_user_orders(product)
        if user_orders is None:
            print("\033[91mError: No user orders found.\033[0m")
            return
        if price is None:
            print("\033[91mError: Current price not found.\033[0m")
            return

        current_time = time.time() # Current time in seconds
        for i, order in user_orders.items():
            if (abs(order["price"] - price) > price_threshold or
                (current_time - (order["timestamp"] / 1e9)) > history_lookback_threshold):
                self.delete_order(order["id"], product)


class AdminTrader(Trader, ABC):
    """
    Admin client class for communicating with the trading server.
    """
    def __init__(self, sender, target, config):
        """
        Initialize the admin client.
        :param sender:  Name of the agent
        :param target:  Server name
        :param config:  Configuration dictionary
        """
        super().__init__(sender, target, config)

    def initialize_liquidity_engine(self, budget, volume):
        """
        Initialize the liquidity engine.
        :param budget: Initial budget
        :param volume: Initial volume - int or dictionary with product specific values
        """
        data = {"budget": budget, "volume": volume, "msg_type": "InitializeLiquidityEngine"}
        message = self.PROTOCOL.encode(data)
        response = session.post(f"{self.BASE_URL}/{self.TRADING_SESSION}",
                                 json={"message": message.decode("utf-8"), "msg_type": data["msg_type"]})
        response = self.parse_response(response)
        if response is None:
            return None
        response["msg_type"] = "UserBalance"
        data = self.PROTOCOL.decode(response)
        return data["user_balance"]

