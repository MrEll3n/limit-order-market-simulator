import json
import pickle
import numpy as np
import pandas as pd
import plotly_resampler
from plotly_resampler import FigureResampler
import plotly.graph_objects as go


def load_data(file_paths):
    """
    Load data from the given file paths and extract user data, timestamps, and mid prices.
    :param file_paths: List of file paths to load data from.
    :return: Tuple containing users data, timestamps, and mid prices.
    """
    users = {}
    timestamps = []
    mid_prices = []
    for file_path in file_paths:
        print(f"Processing file: {file_path}")
        with open(file_path, 'rb') as f:
            data = pickle.load(f)
        for _, order_books in data.items():
            extract_user_data(order_books, users, timestamps, mid_prices)
    return users, timestamps, mid_prices


def extract_user_data(order_books, users, timestamps, mid_prices):
    """
    Extract user data from the order books and populate the users dictionary.
    :param order_books: Dictionary containing order books data and user data.
    :param users: Dictionary of users to populate.
    :param timestamps: List to store timestamps.
    :param mid_prices: List to store mid prices.
    """

    for user, user_data in order_books["users"].items():
        if user not in users:  # Initialize user data if not already present
            users[user] = {}
        users[user]["name"] = user_data.name
        users[user]["budget"] = user_data.budget
        users[user]["num_orders"] = user_data.num_orders

        if "balance" not in users[user]:
            users[user]["balance"] = []
            users[user]["volume"] = []

    for order_book in order_books["order_books"]:
        ob = json.loads(order_book)
        timestamps.append(ob["Timestamp"])

        bids_df = pd.DataFrame(ob["Bids"])
        asks_df = pd.DataFrame(ob["Asks"])
        if not bids_df.empty and not asks_df.empty:
            mid_price = (bids_df['Price'].iloc[0] + asks_df['Price'].iloc[0]) / 2
            mid_prices.append(mid_price)
        else:
            mid_prices.append(None)

        for user, data in ob["UserBalance"].items():
            users[user]["balance"].append(data["balance"])
            users[user]["volume"].append(data["volume"])

    return users, timestamps, mid_prices


def compute_statistics(users, mid_prices, initial_budget=10000):
    """
    Compute statistics for each user based on their final balance, return, and other metrics.
    :param users: Dictionary of users with their data.
    :param mid_prices: List of mid prices.
    :param initial_budget: Initial budget for each user.
    :return: Tuple containing a DataFrame of statistics and stock income.
    """
    stats = []
    stock_income = 0
    for user, data in users.items():
        # Skip market maker and liquidity generator
        if user in ["market_maker", "liquidity_generator"] or data["name"] in ["market_maker", "liquidity_generator"]:
            continue
        stock_income += (initial_budget - data["budget"])

        final_balance = data["budget"]
        volume_series = data["volume"]
        balance_series = data["balance"]

        if balance_series:
            final_balance += balance_series[-1]  # Add the last balance to the final balance
            if mid_prices and mid_prices[-1]:
                final_balance += volume_series[-1] * mid_prices[-1]  # Add the last volume to the final balance

        pnl = final_balance - initial_budget
        avg_balance = np.mean(balance_series) if balance_series else 0

        stats.append({
            "User": user,
            "Name": data["name"],
            "FinalBalance": final_balance,
            "Return (%)": (pnl / initial_budget) * 100 if initial_budget else 0,
            "AvgVolumePerStep": np.mean(volume_series) if volume_series else 0,
            "MaxVolume": max(volume_series, default=0),
            "AvgBalance": avg_balance,
            "NumOrders": data["num_orders"],
        })
    return pd.DataFrame(stats), stock_income


def create_results_table(users, mid_prices, censor=False, top_n=10):
    """
    Create a results table with statistics for each user and save it to a file.
    :param users: Dictionary of users with their data.
    :param mid_prices: List of mid prices.
    :param censor: Boolean flag to censor user UUIDs.
    :param top_n: Number of top users to display (recommended to be 10).
    :return: Table of statistics and top n users.
    """
    stats_df, stock_income = compute_statistics(users, mid_prices)
    stats_df = stats_df.round(2)  # Round to 2 decimal places

    # Sort by FinalBalance column and reset the index
    stats_df = stats_df.sort_values(by='FinalBalance', ascending=False)
    top_n = stats_df.head(top_n)  # Get the top n users

    if censor:
        stats_df = stats_df.drop(columns=['Name'])
        stats_df['User'] = stats_df['User'].apply(lambda x: f"{x[:4]}...{x[-4:]}")  # Censor user UUID
    else:
        stats_df = stats_df.drop(columns=['User'])  # Drop user UUID

    # Reset the index to start from 1 as a rank column
    stats_df = stats_df.reset_index(drop=True)
    stats_df.index = stats_df.index + 1

    stats_df = stats_df.rename(columns={
        "FinalBalance": "Final Balance",
        "Return (%)": "Return (%)",
        "AvgVolumePerStep": "Avg Volume Per Step",
        "MaxVolume": "Max Volume",
        "AvgBalance": "Avg Balance",
        "NumOrders": "Num Orders",
    })

    print(f"Stock fee income: {stock_income}")

    # Save the stats_df to a html file
    stats_df.to_html("statistics.html", index=False, justify='right', float_format='%.2f')
    # Save the stats_df to a csv file
    stats_df.to_csv("statistics.csv", index=False, float_format='%.2f')

    return stats_df, top_n


def plot_best_traders_interactive(users, timestamps, mid_prices, top_10, censor=False):
    """
    Plot the balance of the best traders over time using Plotly.
    :param users: Dictionary of users with their data.
    :param timestamps: List of timestamps.
    :param mid_prices: List of mid prices.
    :param top_10: DataFrame of top 10 users.
    :param censor: Boolean flag to censor user UUIDs.
    """

    # Convert nanoseconds to datetime
    timestamps = pd.to_datetime(timestamps, unit='ns')

    fig = FigureResampler(go.Figure(), default_downsampler=plotly_resampler.MinMaxLTTB(parallel=True))

    user_balances = {}
    for user, data in users.items():
        if user in top_10["User"].values and len(data["balance"]) > 0:
            volume = np.array(data["volume"])
            balance = np.array(data["balance"]) + volume * mid_prices[-1]

            # Pad the balance with 0 in the beginning to match the length of timestamps
            padding = np.zeros(len(timestamps) - len(balance))
            balance = np.concatenate((padding, balance))
            user_balances[user] = balance

    # Add user balances to the plot
    for user in top_10["User"].values:
        if censor:
            user_name = f"{user[:4]}...{user[-4:]}"
        else:
            user_name = f"{users[user]['name']}"
        if user in user_balances:
            fig.add_trace(go.Scatter(
                x=timestamps,
                y=user_balances[user],
                mode='lines',
                name=user_name,
                yaxis="y1"
            ))

    # Add mid prices to the plot
    fig.add_trace(go.Scatter(
        x=timestamps,
        y=mid_prices,
        mode='lines',
        name="Mid Price",
        line=dict(color='black'),
        opacity=0.5,
        yaxis="y2"
    ))

    # Update layout for dual y-axes
    if censor: # Adjust legend position for censored data
        legend_y = 1.4
    else:
        legend_y = 1.55
    fig.update_layout(
        title=dict(
            text="Balance of Best Traders Over Time",
            y=1,
            pad=dict(t=5)),
        xaxis=dict(title="Timestamp"),
        yaxis=dict(title="Balance", side="left"),
        yaxis2=dict(title="Mid Price", overlaying="y", side="right"),
        legend=dict(orientation="h", x=0.5, y=legend_y, xanchor="center"),
        margin=dict(l=50, r=50, t=170, b=50),
        height=500, width=800,
    )

    for trace in fig.data: # Update trace names to remove unwanted characters
        trace.name = trace.name.split("~")[0].strip()
        trace.name = trace.name.replace("[R]", "").strip()

    # Update layout for font size
    fig.update_layout(
        title=dict(
            text="Balance of Best Traders Over Time",
            y=1,
            font=dict(size=20)  # Increase title font size
        ),
        xaxis=dict(
            title=dict(text="Timestamp", font=dict(size=16)),
            tickfont=dict(size=14)
        ),
        yaxis=dict(
            title=dict(text="Balance", font=dict(size=16)),
            tickfont=dict(size=14)
        ),
        yaxis2=dict(
            title=dict(text="Mid Price", font=dict(size=16)),
            tickfont=dict(size=14)
        ),
        legend=dict(
            font=dict(size=14)  # Increase legend font size
        ),
        margin=dict(l=50, r=50, t=170, b=50),
        height=500, width=800,
    )

    # Show the interactive plot
    fig.show()
    # Save the plot as a pdf
    fig.write_image("best_traders_plot.pdf", format="pdf", engine="kaleido")
    # Save the interactive plot as an HTML file
    fig.write_html("best_traders_plot.html")
    # Save the interactive plot as an png file
    fig.write_image("best_traders_plot.png", format="png", engine="kaleido")
