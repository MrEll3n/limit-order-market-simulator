# User Manual

---
## Table of Content

- [About](#about) 
- [Getting Started](#getting%20started)
- [Dashboard](#dashboard)
	- [Active Orders](#active%20orders)
	- [Price Chart](#price%20chart)
	- [Trading Details](#trading%20details)
	- [Order History](#order%20history)
	- [Trading Panel](#trading%20panel)
	- [Top Panel](#top%20panel)
- [Tips for using the simulator](#tips%20for%20using%20the%20simulator)
- [Using python agent](#using%20python%20agent)
	- [handle_market_data(self, message)](#handle_market_data(self%20message))
	- [trade(self, message)](#trade(self%20message))
	- [Agent Deploy](#agent%20deploy)
	- [Other ways to trade with agent](#other%20ways%20to%20trade%20with%20agent)

---
## About

Welcome to Honicoin Crypto, a trading simulator designed to mimic a realistic experience of market mechanics.

This document will guide you through the different components of the interface and how to place, manage and understand trades.

This trading simulator extension is build upon work of **Ing. Vladimíra Kimlová** and this Project would not be possible without her contribution.

---
## Getting Started

Before we dive into vast world of stock trading, best price hunting and graph gazing, on this platform (or almost any other), you cannot do this without an account.

To create an account, go to https://honicoin.site/register where you may insert email and password with verification and continue with register process

![Figure 1: Register page preview][register_page_preview.png]

This way, you will be redirected to login page, where you may continue to sign-in.

---
## Dashboard

Every important action is done in this dashboard below

![Figure 2: Dashboard preview][Dashbord_preview.png]
>Overview of Honicoin Crypto Dashboard showing various panels containing trading information

---
### Active Orders

This panel which you can find on the left of the screen displays all current 🟩**Buy** and 🟥**Sell** orders.

It provides an overview of the market’s ongoing activity, showing the prices and quantities at which buyers and sellers are willing to transact. 

- **Price**: The price per stock unit that is being offered by buyers and sellers
- **Quantity**: The number of shares available at the specified price
- **Buy orders (green)** are the prices at which buyers are willing to purchase stocks.
- **Sell orders (red)** are the prices at which sellers are willing to sell their stocks.
- **Bid price** refers to the highest price that buyers are willing to pay for a stock. 
- **Ask price** refers to the lowest price that sellers are willing to accept for a stock.

![Figure 3: Active orders][active_orders_preview.png]
>Active Orders

---
### Price Chart

The price chart panel right in the middle of the screen shows the movement of stock prices over time. The chart includes:

- **Green Line**: The Best Bid Price, which is the highest price buyers are offering for the stock
- **Red Line**s: The Best Ask Price, which is the lowest price sellers are willing to accept for the stock
- **Yellow dotted line**: The Middle Price, which is an arithmetic mean of the best Bid and Ask Price
- **Product switch**: Use for changing to different product to trade

Use this chart to track market trends and to time your entries and exits into the market. The closer the bid and ask prices are to each other, the higher the liquidity in the market, meaning it is easier to buy and sell shares quickly.

![Figure 4: Price Chart][price_chart_preview.png]
>Price Chart showing last hour of price changes

---
### Trading Details

On the left bottom corner, there is Trading Details panel, which shows current **Mid price** and **Imbalance**
- **Mid Price**: Arithmetic mean of **Best Bid** and **Best Ask**
- **Imbalance**: Represents imbalance of Buy and Sell orders on the market, $Imb \in \langle -1;1 \rangle$

---
### Order History

In the middle bottom you can find logs with details of your previous orders. These details consists of **Side (Buy / Sell)**, **Price**, **Quantity (Qty)**, **Order status** and **Time**.

![Figure 5: Order History][order_history_preview.png]
>Order History filled with cancelled orders

---
### Trading Panel

This section contains the tools needed to interact with the market, including
- Product selection
- Toggle button for changing order to Buy or Sell
- Price
- Quantity

![Figure 6: Trading Panel][trading_panel_preview.png]

---
### Top Panel

The top panel conveniently located at the top displays:
- Your current **Balance**, that can be used to buy different stocks
- **Portfolio**, which shows your current stocks price potential based of **Mid Price**
- User Dropdown button that displays:
	- Email
	- Theme switch
	- Language switch
	- Logout button
 
![Figure 7: Top Panel][top_panel_preview.png]

---
## Tips for using the simulator

- **Set Realistic Price Targets**: Establish clear price targets based on technical
analysis or market sentiment. Set buy orders slightly below the current price
in anticipation of a dip, or place sell orders above the current price if you
expect a rally. Avoid chasing prices too aggressively, as this can lead to
unfavourable entry points.

- **Start Small and Learn Gradually**: Begin with small trades and gradually
increase your exposure as you gain experience. The simulator is a great way to
practice, but real success comes with understanding the mechanics of trading
over time. Patience is key.

- **Stay Calm and Patient**: The market can be volatile, and price movements
can happen quickly. Stay calm and avoid making impulsive decisions based on
short-term fluctuations. Sometimes, it’s best to wait for confirmation before
acting, rather than rushing into trades.

---
## Using python agent

> [!WARNING]
>  You may use agent only with registered account.

For automatic trading you may also use something called an "agent"; a piece of software designated for such task.

The recommended way is to use premade `simple_login_trader.py` provided in [`src/client/agents`](https://github.com/MrEll3n/limit-order-market-simulator/blob/main/src/client/agents/simple_login_trader.py). Please ensure that you have installed all dependencies for this project. See the [README - Installation guide](https://github.com/MrEll3n/limit-order-market-simulator#getting-started) on Trading simulator GitHub.

```python
if __name__ == "__main__":
    HOST = "https://honicoin.site"

    config = requests.get(f"{HOST}/api/config").json()
    config["HOST"] = HOST

    trader = SimpleLoginTrader(name = "BOTname", server = "server", config)

    # Option A: authenticate with email + password (generates a new API key)
    trader.login_via_credentials("bot@example.com", "password :D")

    # Option B: authenticate with a saved API key (reuses existing key)
    # trader.login_via_apikey("sk-your-api-key")

    trader.start_subscribe()
```

- **HOST** is the site, where agent is trying to authenticate to
- Name "BOTname" is the name used in [FIX protocol](https://en.wikipedia.org/wiki/Financial_Information_eXchange) as the sender
- "Server" server argument is destination in FIX protocol

You can use two methods of logging into platform with an Agent:
- A) Authenticate with your email and password - `login_via_credentials()`
- B) Use your API key which you can generate using `/api/account/apikey` endpoint -`login_via_apikey()`

> [!NOTE]
> For sending HTTP requests, you may use [**Bruno app**](https://www.usebruno.com/) or **Curl** tool in terminal.

```bash
# This command sends http request to create your own api key with 
# 'api-key-name' name used in database 

curl -X POST https://honicoin.site/api/account/apikey \ -H "Authorization: Bearer YOUR_API_KEY" \ -H "Content-Type: application/json" \ -d '{"name": "api-key-name"}'
```

### handle_market_data(self, message)

This method is designated for processing and analyzing market data before trading.

### trade(self, message)

Trading logic where you can specify parameters for agent to decide when to buy or sell stocks, which stock and how many units.

### Agent Deploy

>If you are using premade `simple_login_trader.py` 

To deploy your best, smart and intelligent agent, there is nothing easier than running

```bash
python <your_agnet_name>.py
```

and it should connect to Honicoin and you can happily sit and enjoy trading with ease.

### Other ways to trade with agent

> [!WARNING]
> This is purely experimental and have not been tested properly.

You may use REST API endpoints defined in [rest-api.py](https://github.com/MrEll3n/limit-order-market-simulator/blob/main/src/server/rest_api.py) to operate your account as with agent. This is language-agnostic so are not bound solely to Python and FIX protocol.