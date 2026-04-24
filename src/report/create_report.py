import json
import pickle

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def load_data(file_paths):
    """
    Load data from the given file paths.

    :param file_paths: List of file paths to load data from.
    :return: Tuple (users, products) where:
        - users: dict of global user info (name, budget, num_orders)
        - products: dict keyed by product name, each containing:
            "timestamps":  sorted list of nanosecond timestamps
            "mid_prices":  list of mid prices aligned to timestamps
            "user_data":   dict of { user_id: { "balance": [...], "volume": [...] } }
    """
    users = {}
    products = {}

    for file_path in file_paths:
        print(f"Processing file: {file_path}")
        with open(file_path, "rb") as f:
            data = pickle.load(f)

        for product, order_books in data.items():
            if product not in products:
                products[product] = {
                    "timestamps": [],
                    "mid_prices": [],
                    "user_data": {},
                }

            _extract_product_data(order_books, products[product], users)

    # Sort each product's data by timestamp; drop zero-timestamp entries
    for product_data in products.values():
        _sort_product_data(product_data)

    return users, products


def _extract_product_data(order_books, product_data, users):
    """Populate product_data and global users from a single product's order_books block."""

    # Global user metadata (budget, name, orders — not product-specific)
    for user_id, user_obj in order_books["users"].items():
        if user_id not in users:
            users[user_id] = {}
        users[user_id]["name"] = user_obj.name
        users[user_id]["budget"] = user_obj.budget
        users[user_id]["num_orders"] = user_obj.num_orders

    for order_book in order_books["order_books"]:
        ob = json.loads(order_book)

        product_data["timestamps"].append(ob["Timestamp"])

        bids_df = pd.DataFrame(ob["Bids"])
        asks_df = pd.DataFrame(ob["Asks"])
        if not bids_df.empty and not asks_df.empty:
            mid_price = (bids_df["Price"].iloc[0] + asks_df["Price"].iloc[0]) / 2
            product_data["mid_prices"].append(mid_price)
        else:
            product_data["mid_prices"].append(None)

        for user_id, balance_data in ob["UserBalance"].items():
            if user_id not in product_data["user_data"]:
                product_data["user_data"][user_id] = {"balance": [], "volume": []}
            product_data["user_data"][user_id]["balance"].append(
                balance_data["balance"]
            )
            product_data["user_data"][user_id]["volume"].append(balance_data["volume"])


def _sort_product_data(product_data):
    """Sort all arrays in product_data by timestamp; filter zero timestamps."""
    timestamps = product_data["timestamps"]
    n = len(timestamps)

    # Indices of non-zero timestamps, sorted by time
    sort_idx = sorted(
        (i for i in range(n) if timestamps[i] > 0),
        key=lambda i: timestamps[i],
    )
    n_filtered = len(sort_idx)

    product_data["timestamps"] = [timestamps[i] for i in sort_idx]
    product_data["mid_prices"] = [product_data["mid_prices"][i] for i in sort_idx]

    for uid, ud in product_data["user_data"].items():
        bal_len = len(ud["balance"])
        if bal_len == n:
            # Full history — reorder to match sorted timestamps
            ud["balance"] = [ud["balance"][i] for i in sort_idx]
            ud["volume"] = [ud["volume"][i] for i in sort_idx]
        elif bal_len == n_filtered:
            # Already the right length (e.g. loaded from a second file pass) — keep as-is
            pass
        else:
            # Partial history: keep tail entries aligned with the last n timestamps
            tail = (
                sort_idx[n_filtered - bal_len :] if bal_len <= n_filtered else sort_idx
            )
            # Remap using position in sort_idx
            pos_map = {orig: new for new, orig in enumerate(sort_idx)}
            new_bal, new_vol = [], []
            for orig_i in tail:
                if orig_i in pos_map:
                    new_bal.append(ud["balance"][tail.index(orig_i)])
                    new_vol.append(ud["volume"][tail.index(orig_i)])
            ud["balance"] = new_bal
            ud["volume"] = new_vol


def compute_statistics(users, products, initial_budget=10000, excluded_emails=None):
    """
    Compute statistics for each user across all products.

    :param users: Global user dict from load_data.
    :param products: Per-product dict from load_data.
    :param initial_budget: Starting budget.
    :param excluded_emails: Optional list of user emails (names) to exclude from statistics.
    :return: (DataFrame of stats, total stock fee income)
    """
    excluded = set(excluded_emails or [])
    stats = []
    stock_income = 0

    for user_id, user_info in users.items():
        name = user_info.get("name", user_id)
        if user_id in ("market_maker", "liquidity_generator") or name in (
            "market_maker",
            "liquidity_generator",
        ):
            continue

        if name in excluded or user_id in excluded:
            continue

        stock_income += initial_budget - user_info.get("budget", initial_budget)

        final_balance = user_info.get("budget", 0)
        total_volume_series = []
        total_balance_series = []

        for product, product_data in products.items():
            ud = product_data["user_data"].get(user_id)
            if not ud:
                continue
            mid_prices = product_data["mid_prices"]
            last_mid = next((p for p in reversed(mid_prices) if p is not None), None)

            if ud["balance"]:
                total_balance_series.extend(ud["balance"])
                total_volume_series.extend(ud["volume"])
                final_balance += ud["balance"][-1]
                if last_mid is not None:
                    final_balance += ud["volume"][-1] * last_mid

        pnl = final_balance - initial_budget
        stats.append(
            {
                "User": user_id,
                "Name": name,
                "FinalBalance": final_balance,
                "Return (%)": (pnl / initial_budget) * 100 if initial_budget else 0,
                "AvgVolumePerStep": np.mean(total_volume_series)
                if total_volume_series
                else 0,
                "MaxVolume": max(total_volume_series, default=0),
                "AvgBalance": np.mean(total_balance_series)
                if total_balance_series
                else 0,
                "NumOrders": user_info.get("num_orders", 0),
            }
        )

    return pd.DataFrame(stats), stock_income


def create_results_table(users, products, censor=False, top_n=10, excluded_emails=None):
    """
    Create a results table with statistics for each user and save it to a file.

    :param users: Global user dict from load_data.
    :param products: Per-product dict from load_data.
    :param censor: Boolean flag to censor user UUIDs.
    :param top_n: Number of top users to display.
    :param excluded_emails: Optional list of user emails (names) to exclude from the report.
    :return: (stats DataFrame, top_n DataFrame)
    """
    if excluded_emails:
        print("Excluded emails:")
        for email in excluded_emails:
            print(f"  - {email}")

    stats_df, stock_income = compute_statistics(users, products, excluded_emails=excluded_emails)
    stats_df = stats_df.round(2)

    stats_df = stats_df.sort_values(by="FinalBalance", ascending=False)
    top_n_df = stats_df.head(top_n).copy()

    if censor:
        stats_df = stats_df.drop(columns=["Name"])
        stats_df["User"] = stats_df["User"].apply(lambda x: f"{x[:4]}...{x[-4:]}")
    else:
        stats_df = stats_df.drop(columns=["User"])

    stats_df = stats_df.reset_index(drop=True)
    stats_df.index = stats_df.index + 1
    stats_df = stats_df.rename(
        columns={
            "FinalBalance": "Final Balance",
            "AvgVolumePerStep": "Avg Volume Per Step",
            "MaxVolume": "Max Volume",
            "AvgBalance": "Avg Balance",
            "NumOrders": "Num Orders",
        }
    )

    print(f"Stock fee income: {stock_income}")

    stats_df.to_html(
        "statistics.html", index=False, justify="right", float_format="%.2f"
    )
    stats_df.to_csv("statistics.csv", index=False, float_format="%.2f")

    return stats_df, top_n_df


def plot_best_traders_interactive(users, products, top_n, censor=False):
    """
    Plot the balance of the best traders over time, one subplot per product.

    :param users: Global user dict from load_data.
    :param products: Per-product dict from load_data.
    :param top_n: DataFrame of top users (must contain "User" column).
    :param censor: Boolean flag to censor user UUIDs.
    """
    product_names = list(products.keys())
    n_products = len(product_names)
    n_rows = n_products * 2

    # Pre-compute per-product timestamp metadata
    product_meta = {}
    for product in product_names:
        product_data = products[product]
        raw_timestamps = pd.to_datetime(product_data["timestamps"], unit="ns").floor("us")
        raw_mid_prices = product_data["mid_prices"]
        first_valid = next(
            (i for i in range(len(raw_mid_prices)) if raw_mid_prices[i] is not None), 0
        )
        last_valid = next(
            (i for i in range(len(raw_mid_prices) - 1, -1, -1) if raw_mid_prices[i] is not None),
            len(raw_mid_prices) - 1,
        )
        timestamps = raw_timestamps[: last_valid + 1]
        mid_prices = raw_mid_prices[: last_valid + 1]
        product_meta[product] = {
            "raw_timestamps": raw_timestamps,
            "timestamps": timestamps,
            "mid_prices": mid_prices,
            "last_mid": mid_prices[last_valid],
            "x_start": raw_timestamps[first_valid].isoformat(),
            "x_end": raw_timestamps[last_valid].isoformat(),
        }

    # Subplot titles: grouped by product
    subplot_titles = [
        title
        for p in product_names
        for title in (f"{p} — Balance", f"{p} — Portfolio")
    ]

    fig = make_subplots(
        rows=n_rows,
        cols=1,
        subplot_titles=subplot_titles,
        specs=[[{"secondary_y": True}]] * n_rows,
        shared_xaxes=False,
        vertical_spacing=0.12,
    )

    # mode: "balance" = cash only, "portfolio" = cash + stocks * last_mid
    for prod_idx, product in enumerate(product_names):
        for mode_idx, mode in enumerate(["balance", "portfolio"]):
            row_idx = prod_idx * 2 + mode_idx + 1
            is_first_row = row_idx == 1
            meta = product_meta[product]
            product_data = products[product]
            timestamps = meta["timestamps"]
            mid_prices = meta["mid_prices"]
            last_mid = meta["last_mid"]

            for user_id in top_n["User"].values:
                ud = product_data["user_data"].get(user_id)
                if not ud or not ud["balance"]:
                    continue

                cash = np.array(ud["balance"])
                volume = np.array(ud["volume"])
                if mode == "portfolio":
                    y = cash + volume * (last_mid or 0)
                else:
                    y = cash

                n = len(timestamps)
                if len(y) < n:
                    y = np.concatenate((np.zeros(n - len(y)), y))
                elif len(y) > n:
                    y = y[-n:]

                user_name = (
                    f"{user_id[:4]}...{user_id[-4:]}" if censor else users[user_id]["name"]
                )

                fig.add_trace(
                    go.Scatter(
                        x=timestamps,
                        y=y,
                        mode="lines",
                        name=user_name,
                        legendgroup=user_name,
                        showlegend=is_first_row,
                    ),
                    row=row_idx,
                    col=1,
                    secondary_y=False,
                )

            fig.add_trace(
                go.Scatter(
                    x=timestamps,
                    y=mid_prices,
                    mode="lines",
                    name="Mid Price",
                    legendgroup="Mid Price",
                    line=dict(color="black"),
                    opacity=0.5,
                    showlegend=is_first_row,
                ),
                row=row_idx,
                col=1,
                secondary_y=True,
            )

            y_label = "Portfolio Value" if mode == "portfolio" else "Cash Balance"
            fig.update_xaxes(
                title_text="Time",
                title_font=dict(size=14),
                tickangle=-45,
                nticks=10,
                range=[meta["x_start"], meta["x_end"]],
                autorange=False,
                tickformat="%b %d\n%H:%M",
                row=row_idx,
                col=1,
            )
            fig.update_yaxes(
                title_text=y_label,
                title_font=dict(size=14),
                row=row_idx,
                col=1,
                secondary_y=False,
            )
            fig.update_yaxes(
                title_text="Mid Price",
                title_font=dict(size=14),
                row=row_idx,
                col=1,
                secondary_y=True,
            )

    n_traces = len(top_n) + 1
    legend_rows = max(1, -(-n_traces // 2))
    legend_height_px = legend_rows * 25
    chart_height = max(500, 450 * n_rows)
    top_margin = legend_height_px + 120

    fig.update_layout(
        title=dict(text="Balance of Best Traders Over Time", font=dict(size=20), y=1.0, yanchor="top"),
        legend=dict(
            orientation="h",
            x=0.5,
            xanchor="center",
            y=1.05,
            yanchor="bottom",
            font=dict(size=13),
        ),
        margin=dict(l=50, r=50, t=top_margin, b=80),
        height=chart_height,
        width=900,
    )

    fig.show()
    fig.write_html("best_traders_plot.html")
    try:
        fig.write_image("best_traders_plot.pdf", format="pdf")
        fig.write_image("best_traders_plot.png", format="png")
    except Exception as e:
        print(f"[Warning] Image export failed (install kaleido==0.2.1 to fix): {e}")
