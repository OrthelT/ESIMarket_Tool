import pandas as pd
import requests
import json

# Tools to retrieve Jita prices using the Fuzzworks market API
# Sample data to use for testing

def get_jita_prices(vale_data):
    regionid = '10000002'
    base_url = 'https://market.fuzzwork.co.uk/aggregates/?region='
    ids_str = get_vale_type_ids(vale_data)
    url = f'{base_url}{regionid}&types={ids_str}'
    response = requests.get(url)
    data = response.json()
    jita_data = parse_json(data)
    merged_df = merge_vale_data(jita_data, vale_data)
    return merged_df

def get_vale_type_ids(vale_data):
    ids = vale_data['type_id'].to_list()
    ids_str = ','.join(map(str, ids))
    return ids_str

def merge_vale_data(jita_data, vale_data):
    vale_df = vale_data.copy()
    vale_df['type_id'] = vale_df['type_id'].astype(int)
    jita_data.columns = ['type_id', 'jita_sell', 'jita_buy']
    jita_data['type_id'] = jita_data['type_id'].astype(int)
    merged_df = pd.merge(vale_df, jita_data, on='type_id', how='left')
    merged_df = merged_df.reset_index(drop=True)
    merged_df = merged_df[['type_id', 'type_name', 'total_volume_remain', 'price_5th_percentile',
                           'avg_of_avg_price', 'avg_daily_volume', 'group_id', 'jita_sell', 'jita_buy',
                           'group_name', 'category_id', 'category_name']]
    return merged_df

def parse_json(data) -> pd.DataFrame:
    # Prepare data for DataFrame
    rows = []
    for item_id, item_data in data.items():

        buy_data = item_data.get("buy", {})
        sell_data = item_data.get("sell", {})

        rows.append({
            "type_id": item_id,
            "jita_sell": float(sell_data.get("percentile")),
            "jita_buy": float(buy_data.get("percentile")),
        })

    df = pd.DataFrame(rows)
    df['jita_sell'] = df['jita_sell'].round(2)
    df['jita_buy'] = df['jita_buy'].round(2)

    return df

