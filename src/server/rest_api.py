"""
REST API handlers for the trading server.

Provides a clean JSON REST interface for the web frontend while keeping
the existing FIX/WebSocket layer untouched for algorithmic trading clients.

Authentication:
  JWT access token  — short-lived (15 min), returned in JSON body on login.
                       Client sends it as:  Authorization: Bearer <token>
  JWT refresh token — long-lived (7 days), stored in an HttpOnly cookie.
                       Client calls POST /api/auth/refresh to get a new
                       access token without re-entering credentials.
  Refresh tokens are persisted in the SQLite `refresh_tokens` table so they
  can be revoked on logout.

Routes (all prefixed with /api):
  Auth
    POST   /api/auth/register
    POST   /api/auth/login
    POST   /api/auth/refresh
    POST   /api/auth/logout
    GET    /api/auth/me

  Market data (public)
    GET    /api/market/products
    GET    /api/market/orderbook?product=...&depth=...
    GET    /api/market/report?product=...&history_len=...

  Orders  (requires auth — Bearer token)
    POST   /api/orders                     – place new order
    GET    /api/orders/:order_id?product=… – single order status
    PATCH  /api/orders/:order_id           – modify quantity (decrease only)
    DELETE /api/orders/:order_id?product=… – cancel order

  Account (requires auth — Bearer token)
    GET    /api/account/balance?product=…  – budget + balances for one product
    GET    /api/account/balance            – budget + balances for all products
    GET    /api/account/orders?product=…   – user's active orders
    GET    /api/account/history?product=…  – user's order history
"""

import asyncio
import json
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timezone

import bcrypt
import jwt
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
_INITIAL_BUDGET = None
_FIXED_FEE = None
_PERCENTAGE_FEE = None
_ALLOWED_EMAIL_DOMAINS: list[str] = []
_TRADING_SESSION: str = ""
_QUOTE_SESSION: str = ""
_WebSocketHandler = None   # injected to allow broadcasting after REST orders
_CORS_ORIGIN = "http://localhost:3000"  # Vue dev server; overridden by init_rest_api

# JWT configuration
_JWT_SECRET: str = ""                    # injected by init_rest_api
_ACCESS_TOKEN_TTL  = 15 * 60            # 15 minutes  (seconds)
_REFRESH_TOKEN_TTL = 7  * 24 * 3600    # 7 days       (seconds)


def init_rest_api(cursor, conn, user_manager, product_manager, products,
                  initial_budget, fixed_fee, percentage_fee,
                  allowed_email_domains,
                  trading_session, quote_session,
                  websocket_handler,
                  allowed_origin="http://localhost:3000",
                  jwt_secret: str = ""):
    """
    Inject shared server state so REST handlers use the same objects as the
    FIX handlers.  Call this once from server.py before starting the IOLoop.

    jwt_secret  — HMAC-SHA256 key for signing JWTs.  Pass the value of the
                   JWT_SECRET environment variable (or a strong random fallback).
    """
    global _cursor, _conn, _user_manager, _product_manager
    global _products, _INITIAL_BUDGET, _FIXED_FEE, _PERCENTAGE_FEE, _ALLOWED_EMAIL_DOMAINS
    global _TRADING_SESSION, _QUOTE_SESSION
    global _WebSocketHandler, _CORS_ORIGIN, _JWT_SECRET
    _cursor = cursor
    _conn = conn
    _user_manager = user_manager
    _product_manager = product_manager
    _products = products
    _INITIAL_BUDGET = initial_budget
    _FIXED_FEE = fixed_fee
    _PERCENTAGE_FEE = percentage_fee
    _ALLOWED_EMAIL_DOMAINS = allowed_email_domains
    _TRADING_SESSION = trading_session
    _QUOTE_SESSION = quote_session
    _WebSocketHandler = websocket_handler
    _CORS_ORIGIN = allowed_origin
    _JWT_SECRET = jwt_secret or secrets.token_hex(32)


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
        # Expose Authorization so the browser JS can read it if ever sent as a header
        self.set_header("Access-Control-Expose-Headers", "Authorization")

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


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

def _get_user_role(email: str) -> str:
    """Returns the role of a user from the database ('user', 'admin', 'bot')."""
    _cursor.execute("SELECT role FROM users WHERE email=?", (email,))
    row = _cursor.fetchone()
    return row[0] if row else "user"


def _get_valid_roles() -> list[str]:
    """Returns all valid role names from the roles table."""
    _cursor.execute("SELECT name FROM roles ORDER BY name")
    return [r[0] for r in _cursor.fetchall()]


def _create_access_token(email: str) -> str:
    """
    Returns a signed JWT access token valid for _ACCESS_TOKEN_TTL seconds.
    Payload: { sub, role, iat, exp, type='access' }
    """
    now = int(time.time())
    payload = {
        "sub":  email,
        "role": _get_user_role(email),
        "iat":  now,
        "exp":  now + _ACCESS_TOKEN_TTL,
        "type": "access",
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm="HS256")


def _create_refresh_token(email: str) -> str:
    """
    Generates a cryptographically random refresh token, persists it in the
    `refresh_tokens` SQLite table, and returns the token string.
    """
    token = secrets.token_urlsafe(48)
    expires_at = int(time.time()) + _REFRESH_TOKEN_TTL
    _cursor.execute(
        "INSERT INTO refresh_tokens (token, email, expires_at, revoked) VALUES (?, ?, ?, 0)",
        (token, email, expires_at),
    )
    _conn.commit()
    return token


def _verify_access_token(handler) -> tuple[str, str] | tuple[None, None]:
    """
    Reads the Bearer token from the Authorization header, verifies the
    signature and expiry, and returns (email, role), or (None, None).
    """
    auth_header = handler.request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, None
    token = auth_header[len("Bearer "):].strip()
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "access":
            return None, None
        return payload["sub"], payload.get("role", "user")
    except jwt.ExpiredSignatureError:
        _json_error(handler, 401, "Access token expired")
        return None, None
    except jwt.InvalidTokenError:
        return None, None


def _set_refresh_cookie(handler, token: str):
    """Writes the refresh token into a Secure HttpOnly SameSite=Strict cookie."""
    is_https = os.environ.get("HTTPS", "false").lower() == "true"
    handler.set_cookie(
        "refresh_token",
        token,
        httponly=True,
        secure=is_https,
        samesite="Strict",
        max_age=_REFRESH_TOKEN_TTL,
        path="/api/auth",   # cookie is only sent to auth endpoints
    )


def _revoke_refresh_token(token: str, email: str | None = None):
    if email:
        _cursor.execute(
            "UPDATE refresh_tokens SET revoked=1 WHERE token=? AND email=?", (token, email)
        )
    else:
        _cursor.execute(
            "UPDATE refresh_tokens SET revoked=1 WHERE token=?", (token,)
        )
    _conn.commit()

def _revoke_all_refresh_tokens(email: str):
    _cursor.execute(
        "UPDATE refresh_tokens SET revoked=1 WHERE email=?", (email,)
    )
    _conn.commit()

def _get_trading_id(email: str):
    """
    Returns the in-memory trading UUID for a given email, or None.
    """
    return _user_manager.user_name_exists(email)


def _require_auth(handler):
    """
    Validates the Bearer access token from the Authorization header.
    Always sets handler._audit_email and handler._audit_role (even on failure).
    Returns (email, trading_uuid, role), or writes a 401 and returns (None, None, None).
    """
    email, role = _verify_access_token(handler)
    if not email:
        handler._audit_role = "unknown"
        if not handler._finished:
            _json_error(handler, 401, "Not authenticated")
        return None, None, None

    handler._audit_email = email
    handler._audit_role  = role

    trading_id = _get_trading_id(email)
    if not trading_id:
        _cursor.execute("SELECT id FROM users WHERE email=?", (email,))
        if _cursor.fetchone() is None:
            _json_error(handler, 401, "User not found in database")
            return None, None, None
        trading_id = str(uuid.uuid4())
        _user_manager.add_user(email, trading_id, _INITIAL_BUDGET)
    return email, trading_id, role


def _require_role(handler, *allowed_roles: str):
    """
    Like _require_auth but additionally enforces that the user's role is in
    allowed_roles.  Returns (email, trading_uuid, role) or (None, None, None).
    """
    email, trading_id, role = _require_auth(handler)
    if not email:
        return None, None, None
    if role not in allowed_roles:
        _json_error(handler, 403, f"Requires role: {' or '.join(allowed_roles)}")
        return None, None, None
    return email, trading_id, role


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
# Audit log mixin
# ---------------------------------------------------------------------------

class AuditMixin:
    """
    Writes a row to the `audit_log` table after every request finishes.
    Set self._audit_email and self._audit_role in the handler before finishing.
    """

    def initialize(self):
        self._audit_email: str | None = None
        self._audit_role:  str | None = None

    def on_finish(self):
        try:
            _cursor.execute(
                """
                INSERT INTO audit_log
                    (timestamp, email, role, method, path, status_code, ip)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(time.time()),
                    self._audit_email,
                    self._audit_role,
                    self.request.method,
                    self.request.path,
                    self.get_status(),
                    self.request.remote_ip,
                ),
            )
            _conn.commit()
        except Exception as exc:
            logging.warning("audit_log write failed: %s", exc)


# ---------------------------------------------------------------------------
# API key helpers
# ---------------------------------------------------------------------------

def _generate_api_key() -> str:
    """Generate a new random API key with a 'sk-' prefix."""
    return "sk-" + secrets.token_hex(32)


def _hash_api_key(key: str) -> str:
    return bcrypt.hashpw(key.encode(), bcrypt.gensalt()).decode()


def _verify_api_key(key: str) -> str | None:
    """
    Verify an API key and return the associated email, or None if invalid.
    Checks all stored key hashes (bcrypt compare).
    """
    _cursor.execute("SELECT key_hash, email FROM api_keys WHERE active=1")
    for key_hash, email in _cursor.fetchall():
        if bcrypt.checkpw(key.encode(), key_hash.encode()):
            return email
    return None


# ---------------------------------------------------------------------------
# Auth handlers
# ---------------------------------------------------------------------------

class PublicConfigHandler(CORSMixin, tornado.web.RequestHandler):
    """GET /api/config  — public client configuration"""

    def get(self):
        _json_ok(self, {
            "allowedEmailDomains": _ALLOWED_EMAIL_DOMAINS,
            "PRODUCTS":        _products,
            "TRADING_SESSION": _TRADING_SESSION,
            "QUOTE_SESSION":   _QUOTE_SESSION,
        })


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
        if not any(email.endswith(f"@{d}") for d in _ALLOWED_EMAIL_DOMAINS):
            allowed = ", ".join(f"@{d}" for d in _ALLOWED_EMAIL_DOMAINS)
            return _json_error(self, 400, f"Only {allowed} email addresses are allowed")
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

        # Revoke ALL existing refresh tokens for this email
        _revoke_all_refresh_tokens(email)

        # Provision trading UUID if not yet in memory
        trading_id = _user_manager.user_name_exists(email)
        if not trading_id:
            trading_id = str(uuid.uuid4())
            _user_manager.add_user(email, trading_id, _INITIAL_BUDGET)

        access_token  = _create_access_token(email)
        refresh_token = _create_refresh_token(email)
        _set_refresh_cookie(self, refresh_token)

        _json_ok(self, {
            "accessToken": access_token,
            "tokenType":   "Bearer",
            "expiresIn":   _ACCESS_TOKEN_TTL,
            "email":       email,
            "userId":      trading_id,
        })

class AuthRefreshHandler(CORSMixin, tornado.web.RequestHandler):
    """
    POST /api/auth/refresh
    Uses the HttpOnly refresh_token cookie to issue a new access token.
    Rotates the refresh token on every call (refresh token rotation).
    """

    def post(self):
        token = self.get_cookie("refresh_token")
        if not token:
            return _json_error(self, 401, "No refresh token")

        now = int(time.time())
        _cursor.execute(
            "SELECT email, expires_at, revoked FROM refresh_tokens WHERE token=?",
            (token,),
        )
        row = _cursor.fetchone()
        if row is None:
            return _json_error(self, 401, "Unknown refresh token")

        email, expires_at, revoked = row
        if revoked:
            return _json_error(self, 401, "Refresh token has been revoked")
        if expires_at < now:
            return _json_error(self, 401, "Refresh token expired")

        # Refresh token rotation — revoke old, issue new
        _revoke_refresh_token(token)
        new_refresh = _create_refresh_token(email)
        _set_refresh_cookie(self, new_refresh)

        access_token = _create_access_token(email)
        _json_ok(self, {
            "accessToken": access_token,
            "tokenType":   "Bearer",
            "expiresIn":   _ACCESS_TOKEN_TTL,
        })


class AuthLogoutHandler(CORSMixin, tornado.web.RequestHandler):
    """POST /api/auth/logout  — revokes the refresh token and clears the cookie"""

    def post(self):
        token = self.get_cookie("refresh_token")
        if token:
            _revoke_refresh_token(token)
        self.clear_cookie("refresh_token", path="/api/auth")
        _json_ok(self, {"message": "Logged out"})


class AuthMeHandler(CORSMixin, AuditMixin, tornado.web.RequestHandler):
    """GET /api/auth/me  — returns current user info if Bearer token is valid"""

    def get(self):
        email, trading_id, role = _require_auth(self)
        if not email:
            return
        _json_ok(self, {
            "email":  email,
            "userId": trading_id,
            "role":   role,
        })


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
        report = list(_product_manager.get_historical_order_books(product, history_len))
        report.append(_product_manager.get_order_book(product, False).copy().jsonify_order_book())
        _json_ok(self, {"product": product, "history": report})


# ---------------------------------------------------------------------------
# Orders handlers  (auth required)
# ---------------------------------------------------------------------------

class OrdersHandler(CORSMixin, AuditMixin, tornado.web.RequestHandler):
    """
    POST /api/orders   — place a new order
    """

    def post(self):
        from src.order_book.order import Order

        email, user_id, role = _require_auth(self)
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
        original_quantity = quantity

        status = _product_manager.get_matching_engine(product, timestamp).match_order(order)

        if status is None:
            # Order was immediately filled — never entered the book so add_order was never called
            ob = _product_manager.get_order_book(product, False)
            ob.order_history.setdefault(user_id, []).append({
                'id': order.id,
                'timestamp': order.timestamp,
                'side': order.side,
                'price': order.price,
                'quantity': original_quantity,
                'status': 'filled',
            })

        if status is not False:
            fee = _FIXED_FEE + price * quantity * _PERCENTAGE_FEE
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


class OrderDetailHandler(CORSMixin, AuditMixin, tornado.web.RequestHandler):
    """
    GET    /api/orders/:order_id?product=…  — order status
    PATCH  /api/orders/:order_id            — modify quantity
    DELETE /api/orders/:order_id?product=…  — cancel
    """

    def get(self, order_id):
        email, user_id, role = _require_auth(self)
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
        email, user_id, role = _require_auth(self)
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

        result = _product_manager.get_order_book(product, save_history=True, timestamp=time.time_ns())\
            .modify_order_qty(order_id, quantity)
        if not result:
            return _json_error(self, 422, "Quantity modification failed (can only decrease)")

        _json_ok(self, {"orderId": order_id, "status": "modified"})

    def delete(self, order_id):
        email, user_id, role = _require_auth(self)
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

        _product_manager.get_order_book(product, save_history=True, timestamp=time.time_ns()).delete_order(order_id)

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

class AccountApiKeyHandler(CORSMixin, AuditMixin, tornado.web.RequestHandler):
    """
    POST   /api/account/apikey          – generate a new API key
    GET    /api/account/apikey          – list existing API keys (metadata only)
    DELETE /api/account/apikey?id=…     – revoke an API key by id
    """

    def post(self):
        email, _, _ = _require_auth(self)
        if not email:
            return

        try:
            body = json.loads(self.request.body or "{}")
        except json.JSONDecodeError:
            return _json_error(self, 400, "Invalid JSON")

        name = body.get("name", "").strip() or "default"

        # Deactivate existing key with the same name for this user
        _cursor.execute("UPDATE api_keys SET active=0 WHERE email=? AND name=? AND active=1", (email, name))

        raw_key = _generate_api_key()
        key_hash = _hash_api_key(raw_key)
        created_at = int(time.time())

        _cursor.execute(
            "INSERT INTO api_keys (key_hash, email, name, created_at) VALUES (?, ?, ?, ?)",
            (key_hash, email, name, created_at),
        )
        _conn.commit()
        key_id = _cursor.lastrowid

        _json_ok(self, {
            "id":        key_id,
            "key":       raw_key,
            "name":      name,
            "createdAt": created_at,
            "note":      "Store this key safely — it will not be shown again.",
        })

    def get(self):
        email, _, _ = _require_auth(self)
        if not email:
            return

        _cursor.execute(
            "SELECT id, name, created_at, active FROM api_keys WHERE email=? ORDER BY created_at DESC",
            (email,),
        )
        keys = [{"id": row[0], "name": row[1], "createdAt": row[2], "active": bool(row[3])} for row in _cursor.fetchall()]
        _json_ok(self, {"keys": keys})

    def delete(self):
        email, _, _ = _require_auth(self)
        if not email:
            return

        try:
            key_id = int(self.get_argument("id"))
        except (ValueError, TypeError):
            return _json_error(self, 400, "Missing or invalid 'id' parameter")

        _cursor.execute(
            "UPDATE api_keys SET active=0 WHERE id=? AND email=?", (key_id, email)
        )
        _conn.commit()
        if _cursor.rowcount == 0:
            return _json_error(self, 404, "API key not found")

        _json_ok(self, {"message": "API key revoked"})


class AccountBalanceHandler(CORSMixin, AuditMixin, tornado.web.RequestHandler):
    """
    GET /api/account/balance?product=…  – balance + portfolio for one product
    GET /api/account/balance            – balance + portfolio for all products
    """

    def get(self):
        email, user_id, role = _require_auth(self)
        if not email:
            return

        def _mid_price(p):
            ob = _product_manager.get_order_book(p, False)
            bids = list(ob.bids.keys())
            asks = list(ob.asks.keys())
            if not bids or not asks:
                return None
            return (max(bids) + min(asks)) / 2

        product = self.get_argument("product", None)
        _update_post_buy_budget(user_id)
        user = _user_manager.users[user_id]

        if product is not None:
            if product not in _products:
                return _json_error(self, 400, f"Unknown product. Valid: {_products}")

            _update_post_sell_volume(user_id, product)
            ob = _product_manager.get_order_book(product, False)
            volume = ob.user_balance[user_id]["post_sell_volume"]
            price = _mid_price(product)
            return _json_ok(self, {
                "balance": user.post_buy_budget,
                "portfolioValue": round(volume * price, 2) if price is not None else None,
                "products": {
                    product: {
                        "postSellVolume": volume,
                        "price": price,
                        "value": round(volume * price, 2) if price is not None else None,
                    },
                },
            })

        total_value = 0.0
        products_balance = {}
        for p in _products:
            _update_post_sell_volume(user_id, p)
            ob = _product_manager.get_order_book(p, False)
            volume = ob.user_balance[user_id]["post_sell_volume"]
            price = _mid_price(p)
            value = round(volume * price, 2) if price is not None else None
            if value is not None:
                total_value += value
            products_balance[p] = {
                "postSellVolume": volume,
                "price": price,
                "value": value,
            }

        _json_ok(self, {
            "balance": user.post_buy_budget,
            "portfolioValue": round(total_value, 2),
            "products": products_balance,
        })


class AccountOrdersHandler(CORSMixin, AuditMixin, tornado.web.RequestHandler):
    """GET /api/account/orders?product=..."""

    def get(self):
        email, user_id, role = _require_auth(self)
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
# Admin handlers  (role='admin' required)
# ---------------------------------------------------------------------------

class AdminUsersHandler(CORSMixin, AuditMixin, tornado.web.RequestHandler):
    """
    GET   /api/admin/users            — list all users
    PATCH /api/admin/users/:email     — change role of a user
    """

    def get(self):
        email, _, role = _require_role(self, "admin")
        if not email:
            return

        _cursor.execute("SELECT email, role FROM users ORDER BY email")
        rows = _cursor.fetchall()
        _json_ok(self, {"users": [{"email": r[0], "role": r[1]} for r in rows]})


class AdminUserDetailHandler(CORSMixin, AuditMixin, tornado.web.RequestHandler):
    """PATCH /api/admin/users/:email  — { role: 'user'|'admin'|'bot' }"""

    def patch(self, target_email):
        email, _, role = _require_role(self, "admin")
        if not email:
            return

        try:
            body = json.loads(self.request.body)
        except json.JSONDecodeError:
            return _json_error(self, 400, "Invalid JSON")

        new_role = body.get("role", "").strip()
        valid_roles = _get_valid_roles()
        if new_role not in valid_roles:
            return _json_error(self, 400, f"role must be one of: {', '.join(valid_roles)}")

        _cursor.execute("SELECT id FROM users WHERE email=?", (target_email,))
        if not _cursor.fetchone():
            return _json_error(self, 404, f"User {target_email} not found")

        _cursor.execute("UPDATE users SET role=? WHERE email=?", (new_role, target_email))
        _conn.commit()
        _json_ok(self, {"email": target_email, "role": new_role})


class AdminAuditLogHandler(CORSMixin, AuditMixin, tornado.web.RequestHandler):
    """
    GET /api/admin/audit?limit=100&email=...&method=...
    Returns recent audit log entries, newest first.
    """

    def get(self):
        email, _, role = _require_role(self, "admin")
        if not email:
            return

        limit        = min(int(self.get_argument("limit", 100)), 1000)
        filter_email = self.get_argument("email",  None)
        filter_method= self.get_argument("method", None)

        query  = "SELECT timestamp, email, role, method, path, status_code, ip FROM audit_log"
        params = []
        conditions = []
        if filter_email:
            conditions.append("email=?")
            params.append(filter_email)
        if filter_method:
            conditions.append("method=?")
            params.append(filter_method.upper())
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        _cursor.execute(query, params)
        rows = _cursor.fetchall()
        entries = [
            {
                "timestamp":  r[0],
                "email":      r[1],
                "role":       r[2],
                "method":     r[3],
                "path":       r[4],
                "statusCode": r[5],
                "ip":         r[6],
            }
            for r in rows
        ]
        _json_ok(self, {"count": len(entries), "entries": entries})


class AdminRolesHandler(CORSMixin, AuditMixin, tornado.web.RequestHandler):
    """GET /api/admin/roles  — lists all available roles from the roles table"""

    def get(self):
        email, _, role = _require_role(self, "admin")
        if not email:
            return

        _cursor.execute("SELECT name, description FROM roles ORDER BY name")
        rows = _cursor.fetchall()
        _json_ok(self, {"roles": [{"name": r[0], "description": r[1]} for r in rows]})



class AccountOrderHistoryHandler(CORSMixin, AuditMixin, tornado.web.RequestHandler):
    """GET /api/account/history?product=…  — user's full order history for one product"""

    def get(self):
        email, user_id, role = _require_auth(self)
        if not email:
            return

        product = self.get_argument("product", None)
        if not product or product not in _products:
            return _json_error(self, 400, f"Unknown product. Valid: {_products}")

        ob = _product_manager.get_order_book(product, False)
        history = list(ob.order_history.get(user_id, []))
        history.sort(key=lambda x: x['timestamp'], reverse=True)
        _json_ok(self, {"userId": user_id, "product": product, "history": history})


# ---------------------------------------------------------------------------
# Route table  (imported by server.py)
# ---------------------------------------------------------------------------

REST_ROUTES = [
    # Public config
    (r"/api/config",        PublicConfigHandler),
    # Auth
    (r"/api/auth/register", AuthRegisterHandler),
    (r"/api/auth/login",    AuthLoginHandler),
    (r"/api/auth/refresh",  AuthRefreshHandler),
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
    (r"/api/account/apikey",    AccountApiKeyHandler),
    (r"/api/account/balance",   AccountBalanceHandler),
    (r"/api/account/orders",    AccountOrdersHandler),
    (r"/api/account/history",   AccountOrderHistoryHandler),
    # Admin
    (r"/api/admin/users",            AdminUsersHandler),
    (r"/api/admin/users/([^/]+)",    AdminUserDetailHandler),
    (r"/api/admin/audit",            AdminAuditLogHandler),
    (r"/api/admin/roles",            AdminRolesHandler),
]
