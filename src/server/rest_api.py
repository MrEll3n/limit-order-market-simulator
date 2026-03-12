"""
REST API handlers for the trading server.

Provides a clean JSON REST interface for the web frontend while keeping
the existing FIX/WebSocket layer untouched for algorithmic trading clients.

Routes (all prefixed with /api):
  Auth
    POST   /api/auth/register
    POST   /api/auth/login
    POST   /api/auth/logout
    GET    /api/auth/me

  Market data (public)
    GET    /api/market/products
    GET    /api/market/orderbook?product=...&depth=...
    GET    /api/market/report?product=...&history_len=...

  Orders  (requires auth cookie)
    POST   /api/orders                     – place new order
    GET    /api/orders/:order_id?product=… – single order status
    PATCH  /api/orders/:order_id           – modify quantity (decrease only)
    DELETE /api/orders/:order_id?product=… – cancel order

  Account (requires auth cookie)
    GET    /api/account/balance?product=…  – budget + balances
    GET    /api/account/orders?product=…   – user's active orders
"""

import json
import logging
import time
import uuid
import asyncio

import bcrypt
import tornado.web

# ---------------------------------------------------------------------------
# These globals are injected by server.py via `init_rest_api(...)` so the
# REST layer shares the exact same in-memory state as the FIX layer.
# ---------------------------------------------------------------------------
_cursor = None
_conn = None
_user_manager = None
_product_manager = None
_products = []
_INITIAL_BUDGET = 10000
_WebSocketHandler = None   # injected to allow broadcasting after REST orders
_CORS_ORIGIN = "http://localhost:3000"  # Vue dev server; overridden by init_rest_api


def init_rest_api(cursor, conn, user_manager, product_manager, products,
                  initial_budget, websocket_handler, allowed_origin="http://localhost:3000"):
    """
    Inject shared server state so REST handlers use the same objects as the
    FIX handlers.  Call this once from server.py before starting the IOLoop.
    """
    global _cursor, _conn, _user_manager, _product_manager
    global _products, _INITIAL_BUDGET, _WebSocketHandler, _CORS_ORIGIN
    _cursor = cursor
    _conn = conn
    _user_manager = user_manager
    _product_manager = product_manager
    _products = products
    _INITIAL_BUDGET = initial_budget
    _WebSocketHandler = websocket_handler
    _CORS_ORIGIN = allowed_origin


# ---------------------------------------------------------------------------
# CORS mixin — every REST handler inherits this
# ---------------------------------------------------------------------------

class CORSMixin:
    """
    Sets CORS headers on every response so the Vue dev server (port 3000)
    can talk to the Tornado backend (port 8888).

    In production both are served from the same origin so CORS is a no-op,
    but it doesn't hurt to have the headers present.
    """

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", _CORS_ORIGIN)
        self.set_header("Access-Control-Allow-Credentials", "true")
        self.set_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.set_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, X-Requested-With",
        )

    def options(self, *args, **kwargs):  # handles pre-flight for all routes
        self.set_status(204)
        self.finish()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_error(handler, status: int, message: str):
    handler.set_status(status)
    handler.set_header("Content-Type", "application/json")
    handler.finish(json.dumps({"error": message}))


def _json_ok(handler, data: dict, status: int = 200):
    handler.set_status(status)
    handler.set_header("Content-Type", "application/json")
    handler.finish(json.dumps(data))


def _get_authenticated_user(handler):
    """
    Returns the email stored in the secure cookie, or None.
    """
    raw = handler.get_secure_cookie("user")
    return raw.decode() if raw else None


def _get_trading_id(email: str):
    """
    Returns the in-memory trading UUID for a given email, or None.
    """
    return _user_manager.user_name_exists(email)


def _require_auth(handler):
    """
    Returns (email, trading_uuid) or writes a 401 and returns (None, None).
    """
    email = _get_authenticated_user(handler)
    if not email:
        _json_error(handler, 401, "Not authenticated")
        return None, None
    trading_id = _get_trading_id(email)
    if not trading_id:
        # User logged in via web but has not obtained a trading UUID yet.
        # Provision one transparently (same logic as FIX RegisterRequest).
        _cursor.execute("SELECT * FROM users WHERE email=?", (email,))
        if _cursor.fetchone() is None:
            _json_error(handler, 401, "User not found in database")
            return None, None
        trading_id = str(uuid.uuid4())
        _user_manager.add_user(email, trading_id, _INITIAL_BUDGET)
    return email, trading_id


def _update_post_buy_budget(user_id: str):
    initial = _user_manager.users[user_id].budget
    balance = sum(
        _product_manager.get_order_book(p, False).user_balance[user_id]["balance"]
        for p in _products
    )
    buy_value = sum(
        o.price * o.quantity
        for p in _products
        for o in _product_manager.get_order_book(p, False).get_orders_by_user(user_id)
        if o.side == "buy"
    )
    _user_manager.users[user_id].post_buy_budget = initial - buy_value + balance


def _update_post_sell_volume(user_id: str, product: str):
    ob = _product_manager.get_order_book(product, False)
    volume = ob.user_balance[user_id]["volume"]
    sell_vol = sum(
        o.quantity
        for o in ob.get_orders_by_user(user_id)
        if o.side == "sell"
    )
    ob.user_balance[user_id]["post_sell_volume"] = volume - sell_vol


# ---------------------------------------------------------------------------
# Auth handlers
# ---------------------------------------------------------------------------

class AuthRegisterHandler(CORSMixin, tornado.web.RequestHandler):
    """POST /api/auth/register  — { email, password, confirmPassword }"""

    def post(self):
        try:
            body = json.loads(self.request.body)
        except json.JSONDecodeError:
            return _json_error(self, 400, "Invalid JSON")

        email = body.get("email", "").strip()
        password = body.get("password", "")
        confirm = body.get("confirmPassword", "")

        if not email or not password:
            return _json_error(self, 400, "Email and password are required")
        if "@" not in email:
            return _json_error(self, 400, "Invalid email address")
        if password != confirm:
            return _json_error(self, 400, "Passwords do not match")

        _cursor.execute("SELECT id FROM users WHERE email=?", (email,))
        if _cursor.fetchone():
            return _json_error(self, 409, "Email already registered")

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        _cursor.execute(
            "INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed)
        )
        _conn.commit()

        _json_ok(self, {"message": "Registration successful"}, status=201)


class AuthLoginHandler(CORSMixin, tornado.web.RequestHandler):
    """POST /api/auth/login  — { email, password }"""

    def post(self):
        try:
            body = json.loads(self.request.body)
        except json.JSONDecodeError:
            return _json_error(self, 400, "Invalid JSON")

        email = body.get("email", "").strip()
        password = body.get("password", "")

        if not email or not password:
            return _json_error(self, 400, "Email and password are required")

        _cursor.execute("SELECT password FROM users WHERE email=?", (email,))
        row = _cursor.fetchone()
        if row is None:
            return _json_error(self, 401, "Invalid email or password")

        stored_hash = row[0]
        try:
            match = bcrypt.checkpw(password.encode(), stored_hash.encode())
        except Exception:
            return _json_error(self, 500, "Password verification failed")

        if not match:
            return _json_error(self, 401, "Invalid email or password")

        # Provision trading UUID if not yet in memory
        trading_id = _user_manager.user_name_exists(email)
        if not trading_id:
            trading_id = str(uuid.uuid4())
            _user_manager.add_user(email, trading_id, _INITIAL_BUDGET)

        self.set_secure_cookie(
            "user", email,
            samesite="Lax",
            secure=os.environ.get("HTTPS", "false").lower() == "true",
        )
        _json_ok(self, {"email": email, "userId": trading_id})


class AuthLogoutHandler(CORSMixin, tornado.web.RequestHandler):
    """POST /api/auth/logout"""

    def post(self):
        self.clear_cookie("user")
        _json_ok(self, {"message": "Logged out"})


class AuthMeHandler(CORSMixin, tornado.web.RequestHandler):
    """GET /api/auth/me  — returns current user info if authenticated"""

    def get(self):
        email, trading_id = _require_auth(self)
        if not email:
            return
        _json_ok(self, {"email": email, "userId": trading_id})


# ---------------------------------------------------------------------------
# Market data handlers (public — no auth required)
# ---------------------------------------------------------------------------

class MarketProductsHandler(CORSMixin, tornado.web.RequestHandler):
    """GET /api/market/products"""

    def get(self):
        _json_ok(self, {"products": _products})


class MarketOrderBookHandler(CORSMixin, tornado.web.RequestHandler):
    """GET /api/market/orderbook?product=...&depth=..."""

    def get(self):
        from sortedcontainers import SortedDict
        from itertools import islice

        product = self.get_argument("product", None)
        if not product or product not in _products:
            return _json_error(self, 400, f"Unknown product. Valid: {_products}")

        depth = int(self.get_argument("depth", 0))
        ob = _product_manager.get_order_book(product, False).copy()
        if depth > 0:
            ob.bids = SortedDict(islice(reversed(ob.bids.items()), depth))
            ob.asks = SortedDict(islice(ob.asks.items(), depth))

        _json_ok(self, {"product": product, "orderBook": ob.jsonify_order_book(censor=True)})


class MarketReportHandler(CORSMixin, tornado.web.RequestHandler):
    """GET /api/market/report?product=...&history_len=..."""

    def get(self):
        product = self.get_argument("product", None)
        if not product or product not in _products:
            return _json_error(self, 400, f"Unknown product. Valid: {_products}")

        history_len = int(self.get_argument("history_len", -1))
        report = _product_manager.get_historical_order_books(product, history_len)
        report.append(_product_manager.get_order_book(product, False).copy().jsonify_order_book())
        _json_ok(self, {"product": product, "history": report})


# ---------------------------------------------------------------------------
# Orders handlers  (auth required)
# ---------------------------------------------------------------------------

class OrdersHandler(CORSMixin, tornado.web.RequestHandler):
    """
    POST /api/orders   — place a new order
    """

    def post(self):
        from src.order_book.order import Order

        email, user_id = _require_auth(self)
        if not email:
            return

        try:
            body = json.loads(self.request.body)
        except json.JSONDecodeError:
            return _json_error(self, 400, "Invalid JSON")

        product = body.get("product")
        side = body.get("side")
        quantity = body.get("quantity")
        price = body.get("price")

        if not product or product not in _products:
            return _json_error(self, 400, f"Unknown product. Valid: {_products}")
        if side not in ("buy", "sell"):
            return _json_error(self, 400, "side must be 'buy' or 'sell'")
        try:
            quantity = int(quantity)
            price = float(price)
        except (TypeError, ValueError):
            return _json_error(self, 400, "quantity (int) and price (float) are required")
        if quantity <= 0 or price <= 0:
            return _json_error(self, 400, "quantity and price must be positive")

        max_int = 2 ** 31 - 1
        if quantity > max_int or price > max_int:
            return _json_error(self, 400, "quantity or price exceeds maximum value")

        # Budget/volume checks
        if side == "buy":
            _update_post_buy_budget(user_id)
            if _user_manager.users[user_id].post_buy_budget < quantity * price:
                return _json_error(self, 422, "Insufficient budget")

        if side == "sell":
            _update_post_sell_volume(user_id, product)
            user_shares = _product_manager.get_order_book(product, False)\
                .user_balance[user_id]["post_sell_volume"]
            if user_shares < quantity:
                return _json_error(self, 422, "Insufficient share volume")

        # Import server-level ID counter
        import src.server.server as _srv
        timestamp = time.time_ns()
        order = Order(str(_srv.ID), timestamp, user_id, side, quantity, price)
        _srv.ID += 1

        status = _product_manager.get_matching_engine(product, timestamp).match_order(order)

        if status is not False:
            # Apply trading fee
            fixed_fee = 0.01
            percentage_fee = 0.0001
            fee = fixed_fee + price * quantity * percentage_fee
            _user_manager.users[user_id].budget -= fee
            _user_manager.increment_user_orders_counter(user_id)

            # Broadcast updated order book via WebSocket
            if _WebSocketHandler:
                import src.server.server as _srv2
                from src.protocols.FIXProtocol import FIXProtocol
                _proto = FIXProtocol("server")
                broadcast_msg = _proto.encode({
                    "order_book": _product_manager.get_order_book(product, False)
                        .jsonify_order_book(censor=True),
                    "product": product,
                    "msg_type": "MarketDataSnapshot"
                })
                asyncio.ensure_future(_WebSocketHandler.broadcast(broadcast_msg))

        status_str = "open" if status is True else ("filled" if status is None else "rejected")
        _json_ok(
            self,
            {"orderId": order.id, "status": status_str},
            status=201 if status is not False else 422,
        )


class OrderDetailHandler(CORSMixin, tornado.web.RequestHandler):
    """
    GET    /api/orders/:order_id?product=…  — order status
    PATCH  /api/orders/:order_id            — modify quantity
    DELETE /api/orders/:order_id?product=…  — cancel
    """

    def get(self, order_id):
        email, user_id = _require_auth(self)
        if not email:
            return

        product = self.get_argument("product", None)
        if not product or product not in _products:
            return _json_error(self, 400, f"Unknown product. Valid: {_products}")

        ob = _product_manager.get_order_book(product, False)
        order = ob.get_order_by_id(order_id)
        if order is None:
            return _json_error(self, 404, f"Order {order_id} not found")
        if order.user != user_id:
            return _json_error(self, 403, "Order belongs to another user")

        _json_ok(self, order.__json__())

    def patch(self, order_id):
        email, user_id = _require_auth(self)
        if not email:
            return

        try:
            body = json.loads(self.request.body)
        except json.JSONDecodeError:
            return _json_error(self, 400, "Invalid JSON")

        product = body.get("product")
        quantity = body.get("quantity")

        if not product or product not in _products:
            return _json_error(self, 400, f"Unknown product. Valid: {_products}")
        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return _json_error(self, 400, "quantity (int) is required")
        if quantity <= 0:
            return _json_error(self, 400, "quantity must be positive")

        ob = _product_manager.get_order_book(product, False)
        order = ob.get_order_by_id(order_id)
        if order is None:
            return _json_error(self, 404, f"Order {order_id} not found")
        if order.user != user_id:
            return _json_error(self, 403, "Order belongs to another user")

        result = _product_manager.get_order_book(product, time.time_ns())\
            .modify_order_qty(order_id, quantity)
        if not result:
            return _json_error(self, 422, "Quantity modification failed (can only decrease)")

        _json_ok(self, {"orderId": order_id, "status": "modified"})

    def delete(self, order_id):
        email, user_id = _require_auth(self)
        if not email:
            return

        product = self.get_argument("product", None)
        if not product or product not in _products:
            return _json_error(self, 400, f"Unknown product. Valid: {_products}")

        ob = _product_manager.get_order_book(product, False)
        order = ob.get_order_by_id(order_id)
        if order is None:
            return _json_error(self, 404, f"Order {order_id} not found")
        if order.user != user_id:
            return _json_error(self, 403, "Order belongs to another user")

        _product_manager.get_order_book(product, time.time_ns()).delete_order(order_id)

        # Broadcast updated order book
        if _WebSocketHandler:
            from src.protocols.FIXProtocol import FIXProtocol
            _proto = FIXProtocol("server")
            broadcast_msg = _proto.encode({
                "order_book": _product_manager.get_order_book(product, False)
                    .jsonify_order_book(censor=True),
                "product": product,
                "msg_type": "MarketDataSnapshot"
            })
            asyncio.ensure_future(_WebSocketHandler.broadcast(broadcast_msg))

        _json_ok(self, {"orderId": order_id, "status": "cancelled"})


# ---------------------------------------------------------------------------
# Account handlers  (auth required)
# ---------------------------------------------------------------------------

class AccountBalanceHandler(CORSMixin, tornado.web.RequestHandler):
    """GET /api/account/balance?product=..."""

    def get(self):
        email, user_id = _require_auth(self)
        if not email:
            return

        product = self.get_argument("product", None)
        if not product or product not in _products:
            return _json_error(self, 400, f"Unknown product. Valid: {_products}")

        _update_post_buy_budget(user_id)
        _update_post_sell_volume(user_id, product)

        ob = _product_manager.get_order_book(product, False)
        current_balance = ob.user_balance[user_id]
        user = _user_manager.users[user_id]

        _json_ok(self, {
            "userId": user_id,
            "email": email,
            "product": product,
            "budget": user.budget,
            "postBuyBudget": user.post_buy_budget,
            "currentBalance": {
                "balance": current_balance["balance"],
                "volume": current_balance["volume"],
                "postSellVolume": current_balance["post_sell_volume"],
            },
        })


class AccountOrdersHandler(CORSMixin, tornado.web.RequestHandler):
    """GET /api/account/orders?product=..."""

    def get(self):
        email, user_id = _require_auth(self)
        if not email:
            return

        product = self.get_argument("product", None)
        if not product or product not in _products:
            return _json_error(self, 400, f"Unknown product. Valid: {_products}")

        ob = _product_manager.get_order_book(product, False)
        orders = ob.get_orders_by_user(user_id)
        _json_ok(self, {
            "userId": user_id,
            "product": product,
            "orders": {o.id: o.__json__() for o in orders},
        })


# ---------------------------------------------------------------------------
# Route table  (imported by server.py)
# ---------------------------------------------------------------------------

REST_ROUTES = [
    # Auth
    (r"/api/auth/register", AuthRegisterHandler),
    (r"/api/auth/login",    AuthLoginHandler),
    (r"/api/auth/logout",   AuthLogoutHandler),
    (r"/api/auth/me",       AuthMeHandler),
    # Market (public)
    (r"/api/market/products",  MarketProductsHandler),
    (r"/api/market/orderbook", MarketOrderBookHandler),
    (r"/api/market/report",    MarketReportHandler),
    # Orders
    (r"/api/orders",           OrdersHandler),
    (r"/api/orders/([^/]+)",   OrderDetailHandler),
    # Account
    (r"/api/account/balance",  AccountBalanceHandler),
    (r"/api/account/orders",   AccountOrdersHandler),
]
