"""Fetch Jita market prices from the Fuzzworks aggregates API."""

import pandas as pd
import requests


def get_jita_prices(market_data: pd.DataFrame, user_agent: str = "") -> pd.DataFrame:
    """Fetch Jita sell/buy prices and merge with market data.

    Args:
        market_data: DataFrame with a 'type_id' column
        user_agent: User-Agent header string for the HTTP request

    Returns:
        market_data with 'jita_sell' and 'jita_buy' columns added
    """
    region_id = '10000002'
    base_url = 'https://market.fuzzwork.co.uk/aggregates/?region='
    ids_str = _get_type_ids_str(market_data)
    url = f'{base_url}{region_id}&types={ids_str}'
    headers = {'User-Agent': user_agent} if user_agent else {}
    response = requests.get(url, headers=headers)
    data = response.json()
    jita_data = _parse_fuzzworks_json(data)
    return _merge_jita_data(jita_data, market_data)


def _get_type_ids_str(df: pd.DataFrame) -> str:
    """Extract type_ids from DataFrame as comma-separated string."""
    ids = df['type_id'].to_list()
    return ','.join(map(str, ids))


def _merge_jita_data(jita_data: pd.DataFrame, market_data: pd.DataFrame) -> pd.DataFrame:
    """Merge Jita prices with market data on type_id."""
    market_df = market_data.copy()
    market_df['type_id'] = market_df['type_id'].astype(int)
    jita_data.columns = ['type_id', 'jita_sell', 'jita_buy']
    jita_data['type_id'] = jita_data['type_id'].astype(int)
    merged = pd.merge(market_df, jita_data, on='type_id', how='left')
    return merged.reset_index(drop=True)


def _parse_fuzzworks_json(data: dict) -> pd.DataFrame:
    """Parse Fuzzworks aggregates API response into a DataFrame."""
    rows = []
    for item_id, item_data in data.items():
        buy_data = item_data.get("buy", {})
        sell_data = item_data.get("sell", {})
        rows.append({
            "type_id": item_id,
            "jita_sell": float(sell_data.get("percentile", 0)),
            "jita_buy": float(buy_data.get("percentile", 0)),
        })

    df = pd.DataFrame(rows)
    df['jita_sell'] = df['jita_sell'].round(2)
    df['jita_buy'] = df['jita_buy'].round(2)
    return df


if __name__ == '__main__':
    pass
