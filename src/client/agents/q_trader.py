import random
import requests
import os
from dotenv import load_dotenv
import time
import numpy as np
from collections import deque
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), '../../..'))

from src.client.algorithmic_trader import AlgorithmicTrader


class QLearningTrader(AlgorithmicTrader):
    def __init__(self, name, server, config, alpha=0.1, gamma=0.9, epsilon=0.1, epsilon_decay=0.995):
        """
        Initializes the QLearningTrader.
        :param name: Name of the agent
        :param server: Server name
        :param config: Configuration dictionary
        :param alpha: Learning rate (Q-value update step size)
        :param gamma: Discount factor (future reward weighting)
        :param epsilon: Exploration rate (probability of random action)
        :param epsilon_decay: Decay factor for epsilon
        """
        super().__init__(name, server, config)
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay

        self.price_history = {}
        self.q_table = {}  # Q-table: state-action pairs (state -> {action: value})
        self.actions = ["buy", "sell", "hold"]
        self.last_action = {}
        self.last_price = {}
        self.last_trade_time = {}

    def handle_market_data(self, message):
        """
        Processes incoming market data and updates price history.
        - Evaluates the reward for the last action taken based on price changes retroactively.
        :param message: Market data message - dictionary with keys "product", "order_book"
        """
        product = message["product"]

        if product not in self.price_history:
            self.price_history[product] = deque(maxlen=50)

        if (mid_price := self.mid_price()) is None:
            return

        self.price_history[product].append(mid_price)
        self.delete_dispensable_orders(product, mid_price, 1, 60)

        # After trading, the reward is evaluated on the next market data update
        if product in self.last_action and product in self.last_price:
            self.compute_reward(product)

    def get_state(self, product):
        """
        Create a state representation using:
          1. Price change between the last two ticks.
          2. Deviation of the current price from a 5-period moving average.
          3. Volatility (std. deviation) over the last 5 prices.
        :param product: Product name
        :return: A tuple representing the state
        """
        prices = list(self.price_history[product])
        if len(prices) < 5:
            return None

        # Price change between the last two ticks
        price_change = prices[-1] - prices[-2]

        # 5-period moving average and deviation from it
        ma_window = prices[-5:]
        moving_avg = sum(ma_window) / len(ma_window)
        deviation = prices[-1] - moving_avg

        # Volatility: standard deviation over the 5 most recent prices
        volatility = np.std(ma_window)

        # Create a tuple state (rounded for discretization)
        state = (round(price_change, 4), round(deviation, 4), round(volatility, 4))
        return state

    def choose_action(self, state):
        """
        Choose an action based on epsilon-greedy policy (explore vs exploit).
        :param state: Current state of the environment
        """
        if random.uniform(0, 1) < self.epsilon:
            return random.choice(self.actions)  # Exploration (random action)
        else:
            # Exploitation: Select the best action based on Q-values
            if state not in self.q_table:
                self.q_table[state] = {action: 0.0 for action in self.actions}
            return max(self.q_table[state], key=self.q_table[state].get)

    def compute_reward(self, product):
        """
        Compute the reward based on price movement after trade execution.
        :param product: Product name
        """
        action = self.last_action.get(product, None)
        initial_price = self.last_price.get(product, None)
        current_price = self.mid_price()

        if action is None or initial_price is None or current_price is None:
            return 0  # No previous action to evaluate or price is missing

        # Calculate price movement after the trade (profit or loss estimate)
        price_change = current_price - initial_price

        if action == "buy":
            reward = price_change
        elif action == "sell":
            reward = -price_change
        else:
            reward = -abs(price_change)

        # Update the Q-table based on the reward
        state = self.get_state(product)
        if state is not None:
            if state not in self.q_table:
                self.q_table[state] = {action: 0.0 for action in self.actions}

            best_next_action = max(self.q_table[state], key=self.q_table[state].get)
            max_q_value = self.q_table[state][best_next_action]

            # Bellman equation for Q-value update
            self.q_table[state][action] += self.alpha * (reward + self.gamma * max_q_value - self.q_table[state][action])

            # Decay epsilon for exploration vs. exploitation balance
            if random.random() < 0.5:
                self.epsilon = max(0.01, self.epsilon * self.epsilon_decay)

        return reward

    def trade(self, message):
        """
        Executes trades based on the selected action and updates the Q-table based on the reward.
        :param message: Market data message - dictionary with keys "product", "order_book"
        """
        if self.mid_price() is None:
            return
        product = message["product"]

        current_time = time.time()
        if product in self.last_trade_time and (current_time - self.last_trade_time[product]) < 1:
            return  # Don't trade again until at least 1 second has passed

        state = self.get_state(product)
        action = self.choose_action(state)

        if action == "buy":
            buy_price = self.mid_price() * 1.001
            quantity = self.compute_quantity(product, "buy", buy_price)
            if quantity > 0:
                self.put_order({"type": "limit", "side": "buy", "quantity": quantity, "price": buy_price}, product)

        elif action == "sell":
            sell_price = self.mid_price() * 0.999
            quantity = self.compute_quantity(product, "sell", sell_price)
            if quantity > 0:
                self.put_order({"type": "limit", "side": "sell", "quantity": quantity, "price": sell_price}, product)

        # After trading, store the action and price for reward evaluation at the next market data update
        self.last_action[product] = action
        self.last_price[product] = self.mid_price()
        self.last_trade_time[product] = current_time


if __name__ == "__main__":
    load_dotenv(os.path.join(os.path.dirname(__file__), '../../../.env'))
    HOST, PORT = "http://127.0.0.1", 8888
    config = requests.get(f"{HOST}:{PORT}/api/config").json()
    config["HOST"], config["PORT"] = HOST, PORT
    ql_trader = QLearningTrader("ql_trader", "server", config)
    print("[QLearningTrader] Authenticating...")
    ql_trader.login_via_credentials("ql_trader", os.environ.get("BOT_PASSWORD", "changeme"))
    print("[QLearningTrader] Authenticated successfully.")
    print("[QLearningTrader] Starting...")
    ql_trader.start_subscribe()
