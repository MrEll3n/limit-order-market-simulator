import argparse
import asyncio
import glob
import json
import logging
import os
import pickle
import secrets
import signal
import sqlite3
import sys
import time
import traceback
import uuid
from itertools import islice
from pathlib import Path

# Ensure both project root and src/ are on sys.path regardless of cwd
_server_dir = Path(__file__).resolve().parent
sys.path.append(str(_server_dir.parent.parent))  # project root  → enables `from src.*`
sys.path.append(str(_server_dir.parent))         # src/          → enables `from order_book.*`

import bcrypt
import colorlog
import tornado.ioloop
import tornado.web
import tornado.websocket

# Load environment variables from .env file (ignored if file does not exist)
from dotenv import load_dotenv
from sortedcontainers import SortedDict
from tornado import httpserver

from src.order_book.order import Order
from src.order_book.order_book import OrderBook
from src.order_book.product_manager import TradingProductManager
from src.protocols.FIXProtocol import FIXProtocol
from src.server.db_manager import create_user_db
from src.server.rest_api import REST_ROUTES, init_rest_api
from src.server.user_manager import UserManager

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if not _env_path.exists():
    print(f"WARNING: .env file not found at {_env_path}. Using default values.")
load_dotenv(_env_path)


def _validate_env():
    errors = []

    # Must be set
    for var in (
        "JWT_SECRET", "COOKIE_SECRET", "ALLOWED_EMAIL_DOMAINS",
        "HOST", "PORT", "HTTPS", "CORS_ORIGIN",
        "BOT_PASSWORD", "MARKET_MAKER_EMAIL", "MARKET_MAKER_PASSWORD",
        "LIQUIDITY_GENERATOR_EMAIL", "LIQUIDITY_GENERATOR_PASSWORD",
    ):
        if not os.environ.get(var):
            errors.append(f"{var} is not set")

    # Format checks (only if the value is present)
    for var in ("PORT",):
        val = os.environ.get(var, "")
        if val:
            try:
                port = int(val)
                if not (1 <= port <= 65535):
                    errors.append(f"{var}={val} is not a valid port number (must be 1–65535)")
            except ValueError:
                errors.append(f"{var}={val} is not a valid integer")

    host = os.environ.get("HOST", "")
    if host and not host.startswith("http://") and not host.startswith("https://"):
        errors.append(f"HOST={host} must start with http:// or https://")

    https_val = os.environ.get("HTTPS", "").lower()
    if https_val and https_val not in ("true", "false"):
        errors.append(f"HTTPS={https_val} must be 'true' or 'false'")

    cors = os.environ.get("CORS_ORIGIN", "")
    if cors and not cors.startswith("http://") and not cors.startswith("https://"):
        errors.append(f"CORS_ORIGIN={cors} must start with http:// or https://")

    if errors:
        for msg in errors:
            print(f"ERROR: {msg}")
        sys.exit(1)


_validate_env()

colorlog_handler = logging.StreamHandler()
colorlog_handler.setFormatter(
    colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(levelname)s - %(message)s",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )
)
logging.getLogger("tornado.access").disabled = True

SERVER_DIR = Path(__file__).resolve().parent
SRC_DIR = SERVER_DIR.parent
ROOT_DIR = SRC_DIR.parent
CONFIG_PATH = ROOT_DIR / "config" / "server_config.json"
DATA_DIR = ROOT_DIR / "data"

with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
    config = json.load(config_file)
MSG_SEQ_NUM = 0
ID = 0

# Initialize order books and matching engines for multiple products
products = config["PRODUCTS"]

fixed_fee = config["FIXED_FEE"]
percentage_fee = config["PERCENTAGE_FEE"]
INITIAL_BUDGET = config["INITIAL_BUDGET"]
ALLOWED_EMAIL_DOMAINS = [
    d.strip()
    for d in os.environ.get("ALLOWED_EMAIL_DOMAINS", "").split(",")
    if d.strip()
]

product_manager = TradingProductManager(products)
user_manager = UserManager()
db_path = str(SERVER_DIR / "market.db")
if not os.path.exists(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
create_user_db(db_path)  # Create the database and table if they don't exist
conn = sqlite3.connect(db_path)
cursor = conn.cursor()


def _verify_fix_api_key(key: str) -> str | None:
    """Verify an API key for FIX endpoints. Returns the email or None if invalid."""
    cursor.execute("SELECT key_hash, email FROM api_keys WHERE active=1")
    for key_hash, email in cursor.fetchall():
        if bcrypt.checkpw(key.encode(), key_hash.encode()):
            return email
    return None


protocol = FIXProtocol("server")

# Stable cookie secret - read from env so it survives restarts.
# Set COOKIE_SECRET env var in production; falls back to a random value.
HOST = os.environ.get("HOST", "http://127.0.0.1")
PORT = int(os.environ.get("PORT", 8888))

cookie_secret = os.environ.get("COOKIE_SECRET") or os.urandom(32)

# Secret key for signing JWT access tokens.
# Set JWT_SECRET env var in production; falls back to a strong random value.
jwt_secret = os.environ.get("JWT_SECRET") or secrets.token_hex(32)


def product_exists(product):
    """
    Check if the product is valid.
    :param product: Product name
    :return: True if valid, False otherwise
    """
    return product in products


class MainHandler(tornado.web.RequestHandler):
    """
    Main handler for the web server.
    """

    def get(self):
        self.write("This is the trading server")


class MsgHandler(tornado.web.RequestHandler):
    """
    A base handler class that provides the common message handling functionality.
    Subclasses must define `msg_type_handlers`.
    """

    msg_type_handlers = {}  # Must be overridden in subclasses

    def handle_msg(self):
        """
        Handles requests from the client.
        """
        # Verify API key
        api_key = self.request.headers.get("X-API-Key", "")
        if not api_key:
            self.set_status(401)
            self.write({"error": "Missing X-API-Key header"})
            return
        email = _verify_fix_api_key(api_key)
        if not email:
            self.set_status(401)
            self.write({"error": "Invalid API key"})
            return

        try:
            message = json.loads(self.request.body)
        except json.JSONDecodeError:
            self.set_status(400)
            self.write({"error": "Invalid JSON format"})
            return
        logging.info(f"R> {message['message']}")
        msg_type = message["msg_type"]

        handler = self.msg_type_handlers.get(msg_type)  # Call appropriate handler
        if not handler:
            self.set_status(400)
            self.write({"error": f"Unknown message type: {msg_type}"})
            return
        try:
            message = protocol.decode(message)
            user_ID = message["user"]
            if not user_manager.user_exists(user_ID) and msg_type != "RegisterRequest":
                self.set_status(400)
                self.write({"error": "Invalid user ID, please register first"})
                return
            response = handler(message)
        except Exception as e:
            logging.error(e)
            logging.error(traceback.format_exc())
            self.set_status(500)
            self.write({"error": f"Error in handling message: {e}"})
            logging.error(f"Error in handling message: {e}")
            return
        logging.debug(f"S> {response}")
        self.write({"message": response.decode()})

    @staticmethod
    def update_user_post_buy_budget(user_ID):
        """
        Update the user's post-buy budget.
        :param user_ID: User ID
        """
        initial_budget = user_manager.users[user_ID].budget
        balance = sum(
            product_manager.get_order_book(product, False).user_balance[user_ID][
                "balance"
            ]
            for product in products
        )

        # Get all buy orders of the user and update the post-buy budget
        buy_orders_value = sum(
            order.price * order.quantity
            for product in products
            if (order_book := product_manager.get_order_book(product, False))
            for order in order_book.get_orders_by_user(user_ID)
            if order.side == "buy"
        )
        user_manager.users[user_ID].post_buy_budget = (
            initial_budget - buy_orders_value + balance
        )

    @staticmethod
    def update_user_post_sell_volume(user_ID, product):
        """
        Update the user's post-buy budget.
        :param user_ID: User ID
        :param product: Product name
        """
        volume = product_manager.get_order_book(product, False).user_balance[user_ID][
            "volume"
        ]
        # Get all sell orders of the user and update the post-sell volume
        sell_orders_volume = sum(
            order.quantity
            for order in product_manager.get_order_book(
                product, False
            ).get_orders_by_user(user_ID)
            if order.side == "sell"
        )
        product_manager.get_order_book(product, False).user_balance[user_ID][
            "post_sell_volume"
        ] = volume - sell_orders_volume


class TradingHandler(MsgHandler):
    @staticmethod
    def register(message):
        """
        Registers a new user.
        :param message: client message with user budget
        :return: encoded response with user ID
        """
        user_ID = user_manager.user_name_exists(message["user"])
        if user_ID:
            return protocol.encode(
                {"user": user_ID, "msg_type": "RegisterResponse"}
            )  # Return existing user ID
        if user_manager.user_exists(message["user"]):
            return protocol.encode(
                {"user": message["user"], "msg_type": "RegisterResponse"}
            )  # Return existing user ID

        # Check if the user is in the database
        cursor.execute("SELECT * FROM users WHERE email=?", (message["user"],))
        user = cursor.fetchone()
        if user is None:
            raise ValueError("User not found in the database")
        user_ID = str(uuid.uuid4())
        user_manager.add_user(message["user"], user_ID, INITIAL_BUDGET)
        return protocol.encode(
            {"user": user_ID, "msg_type": "RegisterResponse"}
        )  # Return new user ID

    @staticmethod
    def initialize_liq_engine(message):
        """
        Initializes the liquidity engine.
        :param message: client message with user budget
        :return: encoded response with user balance
        """
        user = message["user"]
        budget = message["budget"]
        volume = message["volume"]
        for product in products:
            order_book = product_manager.get_order_book(product, False)
            order_book.modify_user_balance(
                user, 0, volume[product] if isinstance(volume, dict) else volume
            )
            user_manager.set_user_budget(user, budget)
        user_balance = {
            product: product_manager.get_order_book(product, False).user_balance[user]
            for product in products
        }
        return protocol.encode(
            {"user_balance": user_balance, "msg_type": "UserBalance"}
        )

    @staticmethod
    def match_order(message):
        """
        Tries to match an order with the existing orders in the order book,
        remaining quantity is added to the order book.
        :param message: client message with order details (user, side, quantity, price)
        :return: encoded response with order ID and status
        """
        global ID
        product = message["product"]
        if not product_exists(product):
            return protocol.encode(
                {"order_id": -1, "status": False, "msg_type": "ExecutionReport"}
            )

        # Check order details viability
        if message["order"]["side"] not in ["buy", "sell"]:
            return protocol.encode(
                {"order_id": -1, "status": False, "msg_type": "ExecutionReport"}
            )
        if (
            round(message["order"]["quantity"]) <= 0
            or round(message["order"]["price"], 2) <= 0
        ):
            return protocol.encode(
                {"order_id": -1, "status": False, "msg_type": "ExecutionReport"}
            )
        # Check extreme values
        max_int = 2**31 - 1
        if (
            message["order"]["quantity"] > max_int - 1
            or message["order"]["price"] > max_int - 1
        ):
            return protocol.encode(
                {"order_id": -1, "status": False, "msg_type": "ExecutionReport"}
            )

        # If the order is a buy order, check if the user has enough budget to place the order
        if message["order"]["side"] == "buy":
            TradingHandler.update_user_post_buy_budget(message["order"]["user"])
            if (
                user_manager.users[message["order"]["user"]].post_buy_budget
                < message["order"]["quantity"] * message["order"]["price"]
            ):
                return protocol.encode(
                    {"order_id": -1, "status": False, "msg_type": "ExecutionReport"}
                )

        # If the order is a sell order, check if the user has enough shares to sell
        if message["order"]["side"] == "sell":
            TradingHandler.update_user_post_sell_volume(
                message["order"]["user"], product
            )
            user_shares = product_manager.get_order_book(product, False).user_balance[
                message["user"]
            ]["post_sell_volume"]
            if user_shares < message["order"]["quantity"]:
                return protocol.encode(
                    {"order_id": -1, "status": False, "msg_type": "ExecutionReport"}
                )

        timestamp = time.time_ns()
        order = Order(
            str(ID),  # Order ID
            timestamp,  # Timestamp in nanoseconds
            message["order"]["user"],
            message["order"]["side"],
            message["order"]["quantity"],
            message["order"]["price"],
        )
        ID += 1  # Increment order ID
        status = product_manager.get_matching_engine(product, timestamp).match_order(
            order
        )  # Match order
        protocol.set_target(message["order"]["user"])  # Set target to user
        response = protocol.encode(
            {"order_id": order.id, "status": status, "msg_type": "ExecutionReport"}
        )
        if (
            status is not False
        ):  # If the order was added to the order book or fully matched -> apply trading fee
            percentage_based_fee = order.price * order.quantity * percentage_fee
            total_fee = fixed_fee + percentage_based_fee
            user_manager.users[message["order"]["user"]].budget -= total_fee

            user_manager.increment_user_orders_counter(message["order"]["user"])

            # Broadcast the changed order book to all clients
            broadcast_response = protocol.encode(
                {
                    "order_book": product_manager.get_order_book(
                        product, False
                    ).jsonify_order_book(censor=True),
                    "product": product,
                    "msg_type": "MarketDataSnapshot",
                }
            )
            asyncio.ensure_future(WebSocketHandler.broadcast(broadcast_response))
        return response

    @staticmethod
    def delete_order(message):
        """
        Deletes an order from the order book.
        :param message: client message with order ID
        :return: encoded response with order ID and status
        """
        product = message["product"]
        if not product_exists(product):
            return protocol.encode(
                {"order_id": -1, "status": False, "msg_type": "ExecutionReportCancel"}
            )
        order_id = message["order_id"]
        order = product_manager.get_order_book(product, False).get_order_by_id(order_id)
        if order is None:
            return protocol.encode(
                {
                    "order_id": order_id,
                    "status": False,
                    "msg_type": "ExecutionReportCancel",
                }
            )
        if order.user != message["user"]:  # Check if the user is the owner of the order
            return protocol.encode(
                {
                    "order_id": order_id,
                    "status": False,
                    "msg_type": "ExecutionReportCancel",
                }
            )
        product_manager.get_order_book(product, timestamp=time.time_ns()).delete_order(
            order_id
        )
        protocol.set_target(order.user)

        # Broadcast the order book to all clients
        broadcast_response = protocol.encode(
            {
                "order_book": product_manager.get_order_book(
                    product, False
                ).jsonify_order_book(censor=True),
                "product": product,
                "msg_type": "MarketDataSnapshot",
            }
        )
        asyncio.ensure_future(WebSocketHandler.broadcast(broadcast_response))
        return protocol.encode(
            {"order_id": order_id, "status": True, "msg_type": "ExecutionReportCancel"}
        )

    @staticmethod
    def modify_order_qty(message):
        """
        Modifies an order's quantity - only decrease is allowed.
        :param message: client message with order ID and new quantity
        :return: encoded response with order ID and status
        """
        product = message["product"]
        if not product_exists(product):
            return protocol.encode(
                {"order_id": -1, "status": False, "msg_type": "ExecutionReportModify"}
            )
        order_id = message["order_id"]
        quantity = message["quantity"]
        order = product_manager.get_order_book(product, False).get_order_by_id(order_id)
        if order is None:
            return protocol.encode(
                {
                    "order_id": order_id,
                    "status": False,
                    "msg_type": "ExecutionReportModify",
                }
            )
        ret = product_manager.get_order_book(product, time.time_ns()).modify_order_qty(
            order_id, quantity
        )
        protocol.set_target(order.user)
        return protocol.encode(
            {"order_id": order_id, "status": ret, "msg_type": "ExecutionReportModify"}
        )

    msg_type_handlers = {
        "RegisterRequest": lambda message: TradingHandler.register(message),
        "InitializeLiquidityEngine": lambda message: (
            TradingHandler.initialize_liq_engine(message)
        ),
        "NewOrderSingle": lambda message: TradingHandler.match_order(message),
        "OrderCancelRequest": lambda message: TradingHandler.delete_order(message),
        "OrderModifyRequestQty": lambda message: TradingHandler.modify_order_qty(
            message
        ),
    }

    def post(self):
        """
        Handles POST requests from the client.
        """
        self.handle_msg()


class QuoteHandler(MsgHandler):
    @staticmethod
    def order_stats(message):
        """
        Returns the status of an order.
        :param message: client message with order ID
        :return: encoded response with order details
        """
        product = message["product"]
        if not product_exists(product):
            return protocol.encode({"order": None, "msg_type": "OrderStatus"})
        order_book = product_manager.get_order_book(product, False)
        order_id = message["id"]
        order = order_book.get_order_by_id(order_id)
        protocol.set_target(message["user"])
        return protocol.encode({"order": order, "msg_type": "OrderStatus"})

    @staticmethod
    def order_book_request(message):
        """
        Returns the order book.
        :param message: client message with product name
        :return: encoded response with order book data and product name
        """
        product = message["product"]
        depth = message.get("depth", -1)
        if not product_exists(product):
            return protocol.encode(
                {
                    "order_book": None,
                    "product": product,
                    "msg_type": "MarketDataSnapshot",
                }
            )
        order_book = product_manager.get_order_book(product, False)
        order_book = order_book.copy()
        if depth > 0:
            order_book.bids = SortedDict(
                islice(reversed(order_book.bids.items()), depth)
            )
            order_book.asks = SortedDict(islice(order_book.asks.items(), depth))

        order_book_data = order_book.jsonify_order_book(censor=True)
        return protocol.encode(
            {
                "order_book": order_book_data,
                "product": product,
                "msg_type": "MarketDataSnapshot",
            }
        )

    @staticmethod
    def user_data(message):
        """
        Returns the orders of a user.
        :param message: client message with user ID
        :return: encoded response with user orders
        """
        product = message["product"]
        if not product_exists(product):
            return protocol.encode({"user_orders": None, "msg_type": "UserOrderStatus"})
        order_book = product_manager.get_order_book(product, False)
        user_orders = order_book.get_orders_by_user(message["user"])
        user_orders = {order.id: order.__json__() for order in user_orders}
        protocol.set_target(message["user"])
        return protocol.encode(
            {"user_orders": user_orders, "msg_type": "UserOrderStatus"}
        )

    @classmethod
    def user_balance(cls, message):
        """
        Returns records of the balance of a user.
        :param message: client message with user ID
        :return: encoded response with user balance
        """
        cls.update_user_post_buy_budget(message["user"])
        cls.update_user_post_sell_volume(message["user"], message["product"])
        product = message["product"]
        if not product_exists(product):
            return protocol.encode({"user_balance": None, "msg_type": "UserBalance"})

        # Uncomment the following lines if you want to include historical balances
        # historical_books = product_manager.historical_order_books[product]
        # user_balances = [
        #     {**book_data["UserBalance"][message["user"]], 'timestamp': book_data['Timestamp']}
        #     for book in historical_books
        #     if (book_data := json.loads(book)) and message["user"] in book_data["UserBalance"]
        # ]

        # Add current balance
        user_balance = product_manager.get_order_book(product, False).user_balance[
            message["user"]
        ]
        # user_balances[-1]['timestamp'] = time.time_ns()
        protocol.set_target(message["user"])
        user_balances = {
            "current_balance": user_balance,
            "budget": user_manager.users[message["user"]].budget,
            "post_buy_budget": user_manager.users[message["user"]].post_buy_budget,
        }
        return protocol.encode(
            {"user_balance": user_balances, "msg_type": "UserBalance"}
        )

    @staticmethod
    def get_report(message):
        """
        Returns the historical report of the trading session.
        :param message: client message with product name
        :return: encoded response with historical order books
        """
        product = message["product"]
        if not product_exists(product):
            return protocol.encode({"report": None, "msg_type": "CaptureReport"})
        report = product_manager.get_historical_order_books(
            product, message["history_len"]
        )
        # Add current order book to the historical report
        report.append(
            product_manager.get_order_book(product, False).copy().jsonify_order_book()
        )
        return protocol.encode({"history": report, "msg_type": "CaptureReport"})

    msg_type_handlers = {
        "OrderStatusRequest": lambda message: QuoteHandler.order_stats(message),
        "MarketDataRequest": lambda message: QuoteHandler.order_book_request(message),
        "UserOrderStatusRequest": lambda message: QuoteHandler.user_data(message),
        "UserBalanceRequest": lambda message: QuoteHandler.user_balance(message),
        "CaptureReportRequest": lambda message: QuoteHandler.get_report(message),
    }

    def get(self):
        """
        Handles GET requests from the client.
        """
        self.handle_msg()


class WebSocketHandler(tornado.websocket.WebSocketHandler):
    """
    Websocket handler for message exchange between the server and the client.
    """

    clients = set()
    clients_lock = None  # Lock for thread-safe access

    def check_origin(self, origin):
        """
        Allow WebSocket connections from any origin.
        """
        return True

    def open(self):
        """
        Handles new WebSocket connections - adds the client to the subscribed clients.
        """
        self.__class__.clients.add(self)
        logging.info("New WebSocket connection")
        for product in products:
            snapshot = protocol.encode(
                {
                    "order_book": product_manager.get_order_book(
                        product, False
                    ).jsonify_order_book(censor=True),
                    "product": product,
                    "msg_type": "MarketDataSnapshot",
                }
            )
            self.write_message(json.dumps({"message": snapshot.decode()}))

    def on_close(self):
        """
        Handles WebSocket connection close - removes the client from the subscribed clients.
        """
        self.__class__.clients.discard(self)
        logging.info("WebSocket connection closed")

    def on_message(self, message):
        """
        Handles messages from the client.
        """
        pass
        # self.write_message(f">{message}")

    @classmethod
    async def broadcast(cls, message):
        """
        Broadcasts a message to all subscribed clients.
        :param message: message to broadcast
        """
        message_data = {"message": message.decode()}
        if cls.clients_lock is None:
            cls.clients_lock = asyncio.Lock()

        closed_clients = set()

        async with cls.clients_lock:
            for client in list(
                cls.clients
            ):  # Use list to avoid modifying the set during iteration
                if not client.ws_connection or client.ws_connection.is_closing():
                    closed_clients.add(client)
                    continue
                try:
                    await client.write_message(json.dumps(message_data))
                except tornado.websocket.WebSocketClosedError:
                    logging.error("WebSocketClosedError during broadcast")
                    closed_clients.add(client)
                except tornado.iostream.StreamClosedError:
                    logging.error("StreamClosedError during broadcast")
                    closed_clients.add(client)

            # Remove all closed clients after the loop
            for client in closed_clients:
                cls.clients.discard(client)
                logging.info("Removed closed client after failed broadcast")


def make_app():
    """
    Creates the Tornado web application with the defined URL handlers.
    Legacy FIX routes are preserved unchanged; REST routes are added under /api/*.
    :return: Tornado web application instance
    """
    # Inject shared state into the REST layer
    init_rest_api(
        cursor=cursor,
        conn=conn,
        user_manager=user_manager,
        product_manager=product_manager,
        products=products,
        initial_budget=INITIAL_BUDGET,
        fixed_fee=fixed_fee,
        percentage_fee=percentage_fee,
        allowed_email_domains=ALLOWED_EMAIL_DOMAINS,
        trading_session=config["TRADING_SESSION"],
        quote_session=config["QUOTE_SESSION"],
        websocket_handler=WebSocketHandler,
        allowed_origin=os.environ.get("CORS_ORIGIN", "http://localhost:3000"),
        jwt_secret=jwt_secret,
        smtp_host=os.environ.get("SMTP_HOST", ""),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        smtp_user=os.environ.get("SMTP_USER", ""),
        smtp_password=os.environ.get("SMTP_PASSWORD", ""),
        smtp_from=os.environ.get("SMTP_FROM", ""),
    )

    routes = [
        # --- Legacy FIX endpoints (bots / algorithmic clients) ---
        (r"/", MainHandler),
        (f"/{config['TRADING_SESSION']}", TradingHandler),
        (f"/{config['QUOTE_SESSION']}", QuoteHandler),
        (r"/websocket", WebSocketHandler),
    ] + REST_ROUTES

    return tornado.web.Application(
        routes,
        cookie_secret=cookie_secret,
        debug=True,
    )


def load_data():
    """
    Loads the last saved server data from a pickle file.
    """
    global ID
    try:
        # Find the latest pickle file in the data directory
        list_of_files = glob.glob(str(DATA_DIR / "*-server_data.pickle"))
        latest_file = max(list_of_files, key=os.path.getctime)

        with open(latest_file, "rb") as f:
            data = pickle.load(f)

        # Restore product manager and user manager states
        max_id_global = 0
        for product, product_data in data.items():
            order_book_obj = OrderBook()
            order_book, max_id = order_book_obj.from_JSON(
                product_data["order_books"][-1]
            )
            order_book.order_history = product_data.get("order_history", {})
            product_manager.set_order_book(product, order_book)
            product_manager.historical_order_books[product] = product_data[
                "order_books"
            ][:-1]
            max_id_global = max(max_id_global, max_id)

        ID = max_id_global + 1
        user_manager.users = next(iter(data.values()))["users"]
        print("Data successfully loaded from", latest_file)
    except Exception as e:
        print("Error loading data:", e)


def save_data():
    """
    Saves the current server data to a pickle file.
    """
    data_to_save = {}
    for product in products:
        report = product_manager.get_historical_order_books(product, -1)
        report.append(
            product_manager.get_order_book(product, False).copy().jsonify_order_book()
        )
        order_history = product_manager.get_order_book(product, False).order_history
        data_to_save[product] = {
            "order_books": report,
            "order_history": order_history,
            "users": user_manager.users,
        }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_name = str(
        DATA_DIR / f"{time.strftime('%Y-%m-%d_%H-%M-%S')}-server_data.pickle"
    )
    with open(file_name, "wb") as f:
        pickle.dump(data_to_save, f)


def shutdown_server(server):
    """
    Handles server shutdown signals and saves the server data.
    :param server: Tornado server instance
    """
    io_loop = tornado.ioloop.IOLoop.current()

    def stop_handler(signum, frame):
        """
        Handles the shutdown signal and saves the server data.
        :param signum: Signal number
        :param frame: Current stack frame
        """

        def shutdown():
            """
            Shuts down the server and saves the data.
            """

            print("Shutting down server...")
            save_data()

            # Stop accepting new connections
            server.stop()

            print("Shutdown complete, data saved.")
            io_loop.stop()

        io_loop.add_callback(shutdown)

    if sys.platform != "win32":
        signal.signal(signal.SIGQUIT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    parser = argparse.ArgumentParser(description="Trading server")
    parser.add_argument(
        "-l",
        "--load",
        action="store_true",
        help="Load the server data from the last checkpoint",
    )
    parser.add_argument(
        "--log-level",
        default="ERROR",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: ERROR)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level), handlers=[colorlog_handler]
    )

    if args.load:
        load_data()

    app = make_app()
    app = httpserver.HTTPServer(app)
    app.listen(PORT)

    print(f"Server started on {HOST}:{PORT}")
    shutdown_server(app)
    tornado.ioloop.IOLoop.current().start()
