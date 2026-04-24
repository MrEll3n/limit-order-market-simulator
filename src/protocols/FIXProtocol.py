import json
import simplefix
from src.protocols.IProtocol import IProtocol


class FIXProtocol(IProtocol):
    """
    Custom FIX protocol implementation - version 4.4.
    """
    def __init__(self, sender, target="unknown"):
        super().__init__()
        self.version = "FIX.4.4"
        self.BEGIN_STRING = "8=" + self.version
        self.TARGET = "56=" + target
        self.SENDER = "49=" + sender
        self.MSG_SEQ_NUM = 0

        self.parser = simplefix.parser.FixParser()

    def set_target(self, target):
        """
        Set the target ID.
        :param target: Target ID
        :return: None
        """
        self.TARGET = "56=" + target

    def set_sender(self, sender):
        """
        Set the sender ID.
        :param sender: Sender ID
        :return: None
        """
        self.SENDER = "49=" + sender

    def fix_message_init(self):
        """
        Initialize a FIX message with standard header tags.
        :return: simplefix.FixMessage object
        """
        message = simplefix.FixMessage()
        message.append_string(self.BEGIN_STRING, header=True)
        message.append_string(self.TARGET, header=True)
        message.append_string(self.SENDER, header=True)
        message.append_utc_timestamp(52, precision=6, header=True)
        message.append_pair(34, self.MSG_SEQ_NUM, header=True)
        self.MSG_SEQ_NUM += 1
        return message

    def RegisterRequest_encode(self, data):
        """
        Encode the RegisterRequest message.
        :param data: Dictionary with budget
        :return: simplefix.FixMessage object
        """
        budget = data["budget"]
        message = self.fix_message_init()
        message.append_pair(35, "A", header=True)  # MsgType = Logon
        message.append_pair(58, budget)  # Text = Budget; modification of FIX protocol
        return message

    def InitializeLiquidityEngine_encode(self, data):
        """
        Encode the InitializeLiquidityEngine message.
        :param data: Dictionary with budget and volume
        :return: simplefix.FixMessage object
        """
        budget = data["budget"]
        volume = data["volume"]
        message = self.fix_message_init()
        message.append_pair(35, "A", header=True)  # MsgType = Logon
        message.append_pair(44, budget)  # Price; modification of FIX protocol
        if isinstance(volume, int):
            message.append_pair(38, volume) # Quantity; modification of FIX protocol
        else:
            message.append_pair(38, json.dumps(volume))  # Quantity; modification of FIX protocol
        return message

    def OrderStatusRequest_encode(self, data):
        """
        Encode the OrderStatusRequest message.
        :param data: Dictionary with order ID
        :return: simplefix.FixMessage object
        """
        ID = data["ID"]
        product = data["product"]
        message = self.fix_message_init()
        message.append_pair(35, "H", header=True)  # MsgType = OrderStatusRequest
        message.append_pair(41, ID)  # ClOrdID
        message.append_pair(55, product) # Symbol (used as product name)
        return message

    def NewOrderSingle_encode(self, data):
        """
        Encode the NewOrderSingle message.
        :param data: Dictionary with order details (side, quantity, price)
        :return: simplefix.FixMessage object
        """
        order = data["order"]
        product = data["product"]
        message = self.fix_message_init()
        message.append_pair(35, "D", header=True)  # MsgType = NewOrderSingle
        message.append_pair(54, 1 if order['side'] == 'buy' else 2)  # Side
        message.append_pair(38, order['quantity'])  # Quantity
        message.append_pair(44, order['price'])  # Price
        message.append_pair(55, product) # Symbol (used as product name)
        return message

    def OrderCancelRequest_encode(self, data):
        """
        Encode the OrderCancelRequest message.
        :param data: Dictionary with order ID
        :return: simplefix.FixMessage object
        """
        ID = data["ID"]
        product = data["product"]
        message = self.fix_message_init()
        message.append_pair(35, "F", header=True)  # MsgType = OrderCancelRequest
        message.append_pair(41, ID)  # ClOrdID
        message.append_pair(55, product) # Symbol (used as product name)
        return message

    def OrderModifyRequestQty_encode(self, data):
        """
        Encode the OrderModifyRequestQty message.
        :param data: Dictionary with order ID and new quantity
        :return: simplefix.FixMessage object
        """
        ID = data["ID"]
        quantity = data["quantity"]
        product = data["product"]
        message = self.fix_message_init()
        message.append_pair(35, "G", header=True)  # MsgType = OrderCancelReplaceRequest
        message.append_pair(41, ID)  # OrigClOrdID
        message.append_pair(38, quantity)  # Quantity
        message.append_pair(55, product) # Symbol (used as product name)
        return message

    def MarketDataRequest_encode(self, data):
        """
        Encode the MarketDataRequest message.
        :param data: Dictionary with market depth
        :return: simplefix.FixMessage object
        """
        depth = data["depth"]
        product = data["product"]
        message = self.fix_message_init()
        message.append_pair(35, "V", header=True)  # MsgType = MarketDataRequest
        message.append_pair(263, 0)  # SubscriptionRequestType = Snapshot
        message.append_pair(264, depth)  # MarketDepth
        message.append_pair(55, product) # Symbol (used as product name)
        return message

    def UserOrderStatusRequest_encode(self, data):
        """
        Encode the UserOrderStatusRequest message.
        :param data: Dictionary with product name
        :return: simplefix.FixMessage object
        """
        product = data["product"]
        message = self.fix_message_init()
        message.append_pair(35, "AF", header=True)  # MsgType = OrderMassStatusRequest
        message.append_pair(585, 8)  # MassStatusReqType = Status for orders for a PartyID
        message.append_pair(448, self.SENDER.split('=')[1])  # PartyID
        message.append_pair(55, product) # Symbol (used as product name)
        return message

    def UserBalanceRequest_encode(self, data):
        """
        Encode the UserBalanceRequest message.
        :param data: Dictionary with product name
        :return: simplefix.FixMessage object
        """
        product = data["product"]
        message = self.fix_message_init()
        message.append_pair(35, "BB", header=True)  # MsgType = CollateralInquiry
        message.append_pair(55, product) # Symbol (used as product name)
        return message

    def CaptureReportRequest_encode(self, data):
        """
        Encode the CaptureReportRequest message.
        :param data: Dictionary with product name
        :return: simplefix.FixMessage object
        """
        product = data["product"]
        message = self.fix_message_init()
        message.append_pair(35, "AD", header=True)  # MsgType = TradeCaptureReportRequest
        message.append_pair(55, product) # Symbol (used as product name)
        message.append_pair(568, data["history_len"])  # TradeRequestID = History length (number of trades)
        message.append_pair(569, 0)  # TradeRequestType = All trades
        return message

    def RegisterResponse_encode(self, data):
        """
        Encode the RegisterResponse message.
        :param data: Dictionary with user ID and status
        :return: simplefix.FixMessage object
        """
        user = data["user"]
        message = self.fix_message_init()
        message.append_pair(35, "A", header=True)  # MsgType = Logon
        message.append_pair(553, user)  # New unique user ID
        return message

    def OrderStatus_encode(self, data):
        """
        Encode the OrderStatus message.
        :param data: Dictionary with order details (ID, side, quantity, price)
        :return: simplefix.FixMessage object
        """
        order = data["order"]
        message = self.fix_message_init()
        message.append_pair(35, "8")  # ExecutionReport
        message.append_pair(150, "1")  # ExecType = Partially filled
        if order: # Order found
            order = order.__json__()
            message.append_pair(39, "1")  # OrdStatus = Remaining (partially filled) quantity
            message.append_pair(37, order['id'])  # OrderID
            message.append_pair(54, 1 if order['side'] == 'buy' else 2)  # Side
            message.append_pair(151, order['quantity'])  # LeavesQty
            message.append_pair(44, order['price'])  # Price
        else: # Order not found
            message.append_pair(39, "8")  # OrdStatus = Rejected
        return message

    def ExecutionReport_encode(self, data):
        """
        Encode the ExecutionReport message.
        :param data: Dictionary with order ID and status
        :return: simplefix.FixMessage object
        """
        order_id = data["order_id"]
        status = data["status"]
        message = self.fix_message_init()
        message.append_pair(35, "8")
        message.append_pair(37, order_id)
        message.append_pair(150, "0")  # ExecType = New
        if status is True:  # Order partially matched
            message.append_pair(39, "1")
        elif status is None:  # Order fully matched
            message.append_pair(39, "2")
        else:  # Order match failed
            message.append_pair(39, "8")

        return message

    def ExecutionReportCancel_encode(self, data):
        """
        Encode the ExecutionReportCancel message.
        :param data: Dictionary with order ID and status
        :return: simplefix.FixMessage object
        """
        message = self.fix_message_init()
        message.append_pair(37, data["order_id"])
        message.append_pair(39, "4")  # OrdStatus = Canceled
        status = data["status"]
        if status:
            message.append_pair(35, "8")  # ExecutionReport
            message.append_pair(150, "4")  # ExecType = Canceled
        else:
            message.append_pair(35, "9")  # OrderCancelReject

        return message

    def ExecutionReportCancelReplace_encode(self, data):
        """
        Encode the ExecutionReportCancelReplace message.
        :param data: Dictionary with order ID and status
        :return: simplefix.FixMessage object
        """
        message = self.fix_message_init()
        message.append_pair(37, data["order_id"])
        message.append_pair(39, "5")  # OrdStatus = Replaced
        status = data["status"]
        if status:
            message.append_pair(35, "8")
            message.append_pair(150, "5")  # ExecType = Replaced
        else:
            message.append_pair(35, "9")

        return message

    def MarketDataSnapshot_encode(self, data):
        """
        Encode the MarketDataSnapshot message.
        :param data: Dictionary with order book
        :return: simplefix.FixMessage object
        """
        order_book = data["order_book"]
        product = data["product"]
        message = self.fix_message_init()
        message.append_pair(35, "W")
        message.append_pair(55, product) # Symbol (used as product name)
        message.append_pair(58, json.dumps(order_book)) # Simplification of FIX protocol
        return message

    def UserOrders_encode(self, data):
        """
        Encode the UserOrders message.
        :param data: Dictionary with user orders
        :return: simplefix.FixMessage object
        """
        orders = data["user_orders"]
        message = self.fix_message_init()
        message.append_pair(35, "8")
        message.append_pair(150, 2) # Filled
        message.append_pair(58, json.dumps(orders))
        return message

    def UserBalance_encode(self, data):
        """
        Encode the UserBalance message.
        :param data: Dictionary with user balance
        :return: simplefix.FixMessage object
        """
        balance = data["user_balance"]
        message = self.fix_message_init()
        message.append_pair(35, "BA") # MsgType = CollateralReport
        # message.append_pair(908, 1) # Unused - simplification of FIX protocol
        message.append_pair(910, 3) # CollStatus = Accepted
        message.append_pair(58, json.dumps(balance))
        return message

    def CaptureReport_encode(self, data):
        """
        Encode the CaptureReport message.
        :param data: Dictionary with trade history
        :return: simplefix.FixMessage object
        """
        history = data["history"]
        message = self.fix_message_init()
        message.append_pair(35, "AE") # MsgType = TradeCaptureReport
        # Body fields simplification - skipped some mandatory fields

        # Transformed to JSON for simplicity
        # historical_order_books = [order_book.jsonify_order_book() for order_book in history]
        message.append_pair(58, json.dumps(history))
        return message


    def encode(self, msg_data):
        """
        Encode the incoming message to the FIX protocol.
        :param msg_data: Dictionary with message details
        :return: Encoded message
        """
        msg_types_map = {
            # Client -> Server
            "RegisterRequest": lambda data: self.RegisterRequest_encode(data),
            "InitializeLiquidityEngine": lambda data: self.InitializeLiquidityEngine_encode(data),
            "OrderStatusRequest": lambda data: self.OrderStatusRequest_encode(data),
            "NewOrderSingle": lambda data: self.NewOrderSingle_encode(data),
            "OrderCancelRequest": lambda data: self.OrderCancelRequest_encode(data),
            "OrderModifyRequestQty": lambda data: self.OrderModifyRequestQty_encode(data),
            "MarketDataRequest": lambda data: self.MarketDataRequest_encode(data),
            "UserOrderStatusRequest": lambda data: self.UserOrderStatusRequest_encode(data),
            "UserBalanceRequest": lambda data: self.UserBalanceRequest_encode(data),
            "CaptureReportRequest": lambda data: self.CaptureReportRequest_encode(data),

            # Server -> Client
            "RegisterResponse": lambda data: self.RegisterResponse_encode(data),
            "OrderStatus": lambda data: self.OrderStatus_encode(data),
            "ExecutionReport": lambda data: self.ExecutionReport_encode(data),
            "ExecutionReportCancel": lambda data: self.ExecutionReportCancel_encode(data),
            "ExecutionReportModify": lambda data: self.ExecutionReportCancelReplace_encode(data),
            "MarketDataSnapshot": lambda data: self.MarketDataSnapshot_encode(data),
            "UserOrderStatus": lambda data: self.UserOrders_encode(data),
            "UserBalance": lambda data: self.UserBalance_encode(data),
            "CaptureReport": lambda data: self.CaptureReport_encode(data),

        }
        msg_type = msg_data["msg_type"]
        if msg_type not in msg_types_map:
            raise ValueError(f"Unknown message type: {msg_type}")
        message = msg_types_map[msg_type](msg_data)
        byte_buffer = message.encode()
        return byte_buffer

    def parse_message(self, msg):
        """
        Parse the incoming FIX message.
        :param msg: FIX message
        :return: Decoded message
        """
        self.parser.append_buffer(msg)
        message = self.parser.get_message()
        return message

    @staticmethod
    def RegisterRequest_decode(data):
        """
        Decode the RegisterRequest message.
        :param data: FIX message
        :return: Dictionary with user ID and budget
        """
        user = data.get(49).decode()
        budget = float(data.get(58).decode())
        return {"user": user, "budget": budget}

    @staticmethod
    def InitializeLiquidityEngine_decode(data):
        """
        Decode the InitializeLiquidityEngine message.
        :param data: FIX message
        :return: Dictionary with budget and volume
        """
        user = data.get(49).decode()
        budget = float(data.get(44).decode())
        volume = data.get(38).decode()
        if volume.isdigit(): # Check if volume is a number
            volume = int(volume)
        else:
            volume = json.loads(volume)
        return {"user": user, "budget": budget, "volume": volume}

    @staticmethod
    def OrderStatus_decode(data):
        """
        Decode the OrderStatus message.
        :param data: FIX message
        :return: Dictionary with order details (id, side, quantity, price) if found, None otherwise
        """
        if data.get(39).decode() == '8':  # OrderStatus = Rejected
            return None
        order = {'id': data.get(37).decode(), 'side': 'buy' if data.get(54).decode() == '1' else 'sell',
                 'quantity': int(data.get(151).decode()), 'price': float(data.get(44).decode())}
        return order

    @staticmethod
    def ExecutionReport_decode(data):
        """
        Decode the ExecutionReport message.
        :param data: FIX message
        :return: Dictionary with order ID and status (True if partially filled, None if fully filled, False otherwise)
        """
        order_id = data.get(37).decode()
        status = data.get(39).decode()
        if status == '1':
            status = True
        elif status == '2':
            status = None
        else:
            status = False
        return {"order_id": order_id, "status": status}

    @staticmethod
    def ExecutionReportCancel_decode(data):
        """
        Decode the ExecutionReportCancel message.
        :param data: FIX message
        :return: Dictionary with order ID and status (True if successful, False otherwise)
        """
        order_id = data.get(37).decode()
        status = data.get(35).decode() == '8'
        if status: # Execution report
            status = True
        else: # Order Cancel/Replace Reject
            status = False
        return {"order_id": order_id, "status": status}

    @staticmethod
    def MarketDataSnapshot_decode(data):
        """
        Decode the MarketDataSnapshot message.
        :param data: FIX message
        :return: Dictionary with order book
        """
        order_book = json.loads(data.get(58).decode())
        product = data.get(55).decode() # Symbol (used as product name)
        if isinstance(order_book, str):
            order_book = json.loads(order_book)
        return {"order_book": order_book, "product": product}

    @staticmethod
    def RegisterResponse_decode(data):
        """
        Decode the RegisterResponse message.
        :param data: FIX message
        :return: Dictionary with user ID
        """
        user = data.get(553).decode()
        return {"user": user}

    @staticmethod
    def OrderStatusRequest_decode(data):
        """
        Decode the OrderStatusRequest message.
        :param data: FIX message
        :return: Dictionary with order ID
        """
        order_id = data.get(41).decode()
        sender = data.get(49).decode()
        product = data.get(55).decode() # Symbol (used as product name)
        return {"id": order_id, "user": sender, "product": product}

    @staticmethod
    def UserOrders_decode(data):
        """
        Decode the UserOrders message.
        :param data: FIX message
        :return: Dictionary with user orders
        """
        user_orders = json.loads(data.get(58).decode())
        return {"user_orders": user_orders, "user": data.get(49).decode()}

    @staticmethod
    def UserBalance_decode(data):
        """
        Decode the UserBalance message.
        :param data: FIX message
        :return: Dictionary with user balance
        """
        balance = json.loads(data.get(58).decode())
        return {"user_balance": balance, "user": data.get(49).decode()}

    @staticmethod
    def CaptureReport_decode(data):
        """
        Decode the CaptureReport message.
        :param data: FIX message
        :return: Dictionary with trade history
        """
        history = json.loads(data.get(58).decode())
        return {"history": history, "user": data.get(49).decode()}

    @staticmethod
    def NewOrderSingle_decode(data):
        """
        Decode the NewOrderSingle message.
        :param data: FIX message
        :return: Dictionary with order details (user, side, quantity, price)
        """

        order = {
            "user": data.get(49).decode(),
            "side": "buy" if data.get(54).decode() == '1' else 'sell',
            "quantity": int(data.get(38).decode()),
            "price": float(data.get(44).decode())
        }
        return {"order": order, "product": data.get(55).decode(), "user": data.get(49).decode()}

    @staticmethod
    def OrderCancelRequest_decode(data):
        """
        Decode the OrderCancelRequest message.
        :param data: FIX message
        :return: Dictionary with order ID
        """
        order_id = data.get(41).decode()
        product = data.get(55).decode() # Symbol (used as product name)
        return {"order_id": order_id, "product": product, "user": data.get(49).decode()}

    @staticmethod
    def OrderModifyRequestQty_decode(data):
        """
        Decode the OrderModifyRequestQty message.
        :param data: FIX message
        :return: Dictionary with order ID and new quantity
        """
        order_id = data.get(41).decode()
        quantity = int(data.get(38).decode())
        product = data.get(55).decode() # Symbol (used as product name)
        return {"order_id": order_id, "quantity": quantity, "product": product, "user": data.get(49).decode()}

    @staticmethod
    def MarketDataRequest_decode(data):
        """
        Decode the MarketDataRequest message.
        :param data: FIX message
        :return: Dictionary with market depth
        """
        depth = int(data.get(264).decode())
        product = data.get(55).decode() # Symbol (used as product name)
        return {"depth": depth, "product": product, "user": data.get(49).decode()}

    @staticmethod
    def UserOrderStatusRequest_decode(data):
        """
        Decode the UserOrderStatusRequest message.
        :param data: FIX message
        :return: Dictionary with user ID
        """
        user = data.get(49).decode()
        product = data.get(55).decode() # Symbol (used as product name)
        return {"user": user, "product": product}

    @staticmethod
    def UserBalanceRequest_decode(data):
        """
        Decode the UserBalanceRequest message.
        :param data: FIX message
        :return: Dictionary with product name
        """
        raw_user = data.get(49)
        raw_product = data.get(55)
        if raw_user is None:
            raise ValueError("Missing required FIX tag 49 (SenderCompID) in UserBalanceRequest")
        if raw_product is None:
            raise ValueError("Missing required FIX tag 55 (Symbol) in UserBalanceRequest")
        user = raw_user.decode()
        product = raw_product.decode()
        return {"user": user, "product": product}

    @staticmethod
    def CaptureReportRequest_decode(data):
        """
        Decode the CaptureReportRequest message.
        :param data: FIX message
        :return: Dictionary with product name
        """
        raw_user = data.get(49)
        raw_product = data.get(55)
        if raw_user is None:
            raise ValueError("Missing required FIX tag 49 (SenderCompID) in CaptureReportRequest")
        if raw_product is None:
            raise ValueError("Missing required FIX tag 55 (Symbol) in CaptureReportRequest")
        history_len = int(data.get(568).decode())
        return {"product": raw_product.decode(), "history_len": history_len, "user": raw_user.decode()}

    def decode(self, message):
        """
        Decode the incoming message from the FIX protocol.
        :param message: Dictionary with message details
        :return: Decoded message
        """
        msg_type = message['msg_type']
        try:
            message = self.parse_message(message['message'])
        except Exception as e:
            print(f"Error parsing message: {e}")
            return None
        msg_types_map = {
            # Client -> Server
            "RegisterRequest": lambda msg: self.RegisterRequest_decode(msg),
            "InitializeLiquidityEngine": lambda msg: self.InitializeLiquidityEngine_decode(msg),
            "OrderStatus": lambda msg: self.OrderStatus_decode(msg),
            "ExecutionReport": lambda msg: self.ExecutionReport_decode(msg),
            "ExecutionReportCancel": lambda msg: self.ExecutionReportCancel_decode(msg),
            "ExecutionReportModify": lambda msg: self.ExecutionReportCancel_decode(msg),
            "MarketDataSnapshot": lambda msg: self.MarketDataSnapshot_decode(msg),
            "UserOrderStatus": lambda msg: self.UserOrders_decode(msg),
            "UserBalance": lambda msg: self.UserBalance_decode(msg),
            "CaptureReport": lambda msg: self.CaptureReport_decode(msg),

            # Server -> Client
            "RegisterResponse": lambda msg: self.RegisterResponse_decode(msg),
            "OrderStatusRequest": lambda msg: self.OrderStatusRequest_decode(msg),
            "NewOrderSingle": lambda msg: self.NewOrderSingle_decode(msg),
            "OrderCancelRequest": lambda msg: self.OrderCancelRequest_decode(msg),
            "OrderModifyRequestQty": lambda msg: self.OrderModifyRequestQty_decode(msg),
            "MarketDataRequest": lambda msg: self.MarketDataRequest_decode(msg),
            "UserOrderStatusRequest": lambda msg: self.UserOrderStatusRequest_decode(msg),
            "UserBalanceRequest": lambda msg: self.UserBalanceRequest_decode(msg),
            "CaptureReportRequest": lambda msg: self.CaptureReportRequest_decode(msg),


        }
        data = msg_types_map[msg_type](message)
        return data
