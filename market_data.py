"""
Pure data processing functions for ESI market data.

No I/O, no network calls, no globals — just DataFrame transformations.
"""

import pandas as pd


def filter_orders(type_ids: list[int], orders_df: pd.DataFrame) -> pd.DataFrame:
    """Filter orders DataFrame to only include items in type_ids list."""
    return orders_df[orders_df['type_id'].isin(type_ids)]


def aggregate_sell_orders(orders_data: pd.DataFrame) -> pd.DataFrame:
    """Aggregate sell orders by type_id: total volume, min price, 5th percentile price."""
    sell_orders = orders_data[orders_data['is_buy_order'] == False]

    grouped_df = sell_orders.groupby('type_id')['volume_remain'].sum().reset_index()
    grouped_df.columns = ['type_id', 'total_volume_remain']

    min_price_df = sell_orders.groupby('type_id')['price'].min().reset_index()
    min_price_df.columns = ['type_id', 'min_price']

    percentile_5th_df = sell_orders.groupby('type_id')['price'].quantile(0.05).reset_index()
    percentile_5th_df.columns = ['type_id', 'price_5th_percentile']

    merged_df = pd.merge(grouped_df, min_price_df, on='type_id')
    merged_df = pd.merge(merged_df, percentile_5th_df, on='type_id')

    return merged_df


def compute_history_stats(history_df: pd.DataFrame, days: int = 30) -> pd.DataFrame:
    """Compute average price and volume from recent history.

    Args:
        history_df: Raw market history DataFrame with 'date', 'type_id', 'average', 'volume'
        days: Number of recent days to include in calculations

    Returns:
        DataFrame with type_id, avg_of_avg_price, avg_daily_volume
    """
    history_df = history_df.copy()
    history_df['date'] = pd.to_datetime(history_df['date'])
    cutoff = pd.to_datetime('today') - pd.DateOffset(days=days)
    recent = history_df[history_df['date'] >= cutoff]

    stats = recent.groupby('type_id').agg(
        avg_of_avg_price=('average', 'mean'),
        avg_daily_volume=('volume', 'mean'),
    ).reset_index()

    stats['avg_of_avg_price'] = stats['avg_of_avg_price'].round(2)
    stats['avg_daily_volume'] = stats['avg_daily_volume'].round(2)
    return stats


def merge_market_stats(
    sell_orders: pd.DataFrame,
    history_df: pd.DataFrame,
    sde_names: dict[int, str],
) -> pd.DataFrame:
    """Merge aggregated sell orders with history stats and item names.

    Args:
        sell_orders: Output of aggregate_sell_orders()
        history_df: Raw market history data
        sde_names: Dict mapping type_id -> type_name

    Returns:
        Final merged DataFrame with columns:
        type_id, type_name, total_volume_remain, price_5th_percentile,
        min_price, avg_of_avg_price, avg_daily_volume
    """
    history_stats = compute_history_stats(history_df)
    merged = pd.merge(sell_orders, history_stats, on='type_id', how='left')

    # Apply SDE names
    name_df = pd.DataFrame([
        {'type_id': tid, 'type_name': name}
        for tid, name in sde_names.items()
    ])
    final = pd.merge(merged, name_df, on='type_id', how='left')

    columns = [
        'type_id', 'type_name', 'total_volume_remain',
        'price_5th_percentile', 'min_price',
        'avg_of_avg_price', 'avg_daily_volume',
    ]
    return final[columns]
