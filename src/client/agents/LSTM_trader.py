import pandas as pd
import torch.nn as nn
import torch.optim as optim
import torch
import requests
import os
from dotenv import load_dotenv
import numpy as np
from collections import deque
from sklearn.preprocessing import MinMaxScaler
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '../../..'))

from src.client.algorithmic_trader import AlgorithmicTrader


class LSTMPricePredictor(nn.Module):

    def __init__(self, input_size=7, hidden_size=64, num_layers=2):
        """
        Initialize the LSTM model.
        :param input_size: Number of input features
        :param hidden_size: Number of hidden units
        :param num_layers: Number of LSTM layers
        """
        super(LSTMPricePredictor, self).__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
        self.fc = nn.Linear(hidden_size, 2)  # Output: Predicted bid & ask

    def forward(self, x):
        """
        Forward pass through the LSTM model.
        :param x: Input tensor
        :return: Output tensor
        """
        out, _ = self.lstm(x)
        out = self.fc(out[:, -1, :])  # Take last step output
        return out


class DeepLearningTrader(AlgorithmicTrader):
    def __init__(self, name, server, config, history_len=20, price_threshold=0.01):
        """
        Initialize the DeepLearningTrader agent with LSTM model.
        :param name: Name of the agent
        :param server: Server name
        :param config: Configuration dictionary
        :param history_len: Length of historical data window
        :param price_threshold: Price threshold for trading
        """
        super().__init__(name, server, config)
        self.window_size = history_len
        self.price_threshold = price_threshold
        self.prices = {}
        self.volumes = {}
        self.imbalances = {}
        self.trade_history = deque(maxlen=1000)  # Store past trades for analysis

        # Data preprocessing
        self.scaler = MinMaxScaler(feature_range=(-1, 1))
        self.scaler_fitted = False

        # Select model
        self.model = LSTMPricePredictor()
        self.criterion = nn.MSELoss()
        self.optimizer = optim.Adam(self.model.parameters(), lr=0.001)
        self.replay_buffer = deque(maxlen=500)  # Store training samples for batch learning

    def handle_market_data(self, message):
        """
        Processes incoming market data and updates historical features.
        - Stores bid/ask prices, volumes, and imbalance indices.
        - Prepares data for LSTM training and prediction.
        :param message: Market data message - dictionary with keys "product", "order_book"
        """
        product = message["product"]
        if product not in self.prices:
            self.prices[product] = {"bid": [], "ask": []}
            self.volumes[product] = {"bid": [], "ask": []}
            self.imbalances[product] = []

        # Store order book data: bid, ask prices and volumes and calculate imbalance index
        bids = message["order_book"]["Bids"]
        asks = message["order_book"]["Asks"]
        bids_df = pd.DataFrame(bids)
        asks_df = pd.DataFrame(asks)
        self.prices[product]["bid"].append(bids[0]["Price"])
        self.prices[product]["ask"].append(asks[0]["Price"])
        self.volumes[product]["bid"].append(bids[0]["Quantity"])
        self.volumes[product]["ask"].append(asks[0]["Quantity"])
        self.imbalances[product].append(self.imbalance_index(asks_df['Quantity'].values, bids_df['Quantity'].values))

        # Trim the data
        for key in ["bid", "ask"]:
            self.prices[product][key] = self.prices[product][key][-self.window_size:]
        for key in ["bid", "ask"]:
            self.volumes[product][key] = self.volumes[product][key][-self.window_size:]
        self.imbalances[product] = self.imbalances[product][-self.window_size:]

        # Ensure scaler is fitted
        if len(self.prices[product]["bid"]) >= self.window_size and not self.scaler_fitted:
            features = self.get_features(product)
            self.scaler.fit(features)
            self.scaler_fitted = True

        # Add new sample to replay buffer
        if len(self.prices[product]["bid"]) >= self.window_size:
            features = self.get_features(product)
            scaled_features = self.scaler.transform(features)
            x = torch.tensor(scaled_features[:-1], dtype=torch.float32).unsqueeze(0)
            y = torch.tensor(scaled_features[-1, :2], dtype=torch.float32)
            self.replay_buffer.append((x, y))

    def get_features(self, product):
        """
        Computes additional features for LSTM input.
        - Includes bid/ask prices, volumes, imbalance indices, spread, and momentum.
        - Deletes dispensable orders based on the latest mid-price.
        :param product: Product name
        :return: Feature matrix
        """
        bids = self.prices[product]["bid"]
        asks = self.prices[product]["ask"]
        bid_volumes = self.volumes[product]["bid"]
        ask_volumes = self.volumes[product]["ask"]
        imbalances = self.imbalances[product]

        mid_prices = (np.array(bids) + np.array(asks)) / 2
        spread = np.array(asks) - np.array(bids)
        momentum = np.diff(mid_prices, prepend=mid_prices[0])

        # Delete dispensable orders
        self.delete_dispensable_orders(product, mid_prices[-1], 1, 60)

        return np.column_stack((bids, asks, bid_volumes, ask_volumes, imbalances, spread, momentum))

    def predict_price(self, product):
        """
        Predict the next bid and ask prices using the LSTM model.
        :param product: Product name
        :return: Tuple of predicted bid and ask prices
        """
        if len(self.prices[product]["bid"]) < self.window_size:
            return self.prices[product]["bid"][-1], self.prices[product]["ask"][-1]

        features = self.get_features(product)
        scaled_features = self.scaler.transform(features)

        x = torch.tensor(scaled_features[:-1], dtype=torch.float32).unsqueeze(0)

        self.model.eval()
        with torch.no_grad():
            pred = self.model(x).squeeze().numpy()

        placeholder = np.zeros((1, features.shape[1]))
        placeholder[0, :2] = pred
        bid_pred, ask_pred = self.scaler.inverse_transform(placeholder)[0][:2]

        return bid_pred, ask_pred

    def train_model(self):
        """
        Train the LSTM using mini-batch gradient descent.
        """
        if len(self.replay_buffer) < self.window_size + 1:
            return

        batch_size = min(32, len(self.replay_buffer))
        batch = np.random.choice(len(self.replay_buffer), batch_size, replace=False)
        x_batch, y_batch = zip(*[self.replay_buffer[i] for i in batch])

        x_train = torch.stack(x_batch).squeeze(1)
        y_train = torch.stack(y_batch)

        self.model.train()
        self.optimizer.zero_grad()
        output = self.model(x_train)
        loss = self.criterion(output, y_train)
        loss.backward()
        self.optimizer.step()

    def trade(self, message):
        """
        Executes trades based on predicted prices and current market conditions.
        - Places buy or sell orders if the predicted prices meet the threshold.
        :param message: Market data message - dictionary with keys "product", "order_book"
        """
        product = message["product"]
        self.train_model()

        predicted_bid, predicted_ask = self.predict_price(product)
        current_bid, current_ask = self.prices[product]["bid"][-1], self.prices[product]["ask"][-1]
        self.bid_ask_trade((current_bid, current_ask), (predicted_bid, predicted_ask), self.price_threshold, product)



if __name__ == "__main__":
    load_dotenv()
    HOST, PORT = "http://127.0.0.1", 8888
    config = requests.get(f"{HOST}:{PORT}/api/config").json()
    config["HOST"], config["PORT"] = HOST, PORT
    lstm_trader = DeepLearningTrader("lstm_trader", "server", config)
    lstm_trader.login_via_credentials("lstm_trader", os.environ.get("BOT_PASSWORD", "changeme"))
    lstm_trader.start_subscribe()
