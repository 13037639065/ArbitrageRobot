import os
import time
import pathlib
import requests
import json
from binance.um_futures import UMFutures
from configparser import ConfigParser

SYMBOL = "BTCUSDT"

def wxwork_message(url, message):
    requests.post(
        url,
        json={"msgtype": "text", "text": {"content": message}},
        timeout=3
    )

def get_api_key():
    config = ConfigParser()
    config_file_path = os.path.join(
        pathlib.Path(__file__).parent.resolve(), ".", "config.ini"
    )
    config.read(config_file_path)
    return config["keys"]["api_key"], config["keys"]["api_secret"], config["keys"]["webhook"]


if __name__ == '__main__':
    key,secret,webhook_url = get_api_key()
    umFutures = UMFutures(key=key, secret=secret)
    print("===========================")
    while True:
        try:
            # 打印当前时间
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{current_time}] 查询合约订单状态...")
            
            # 查询当前合约持有
            open_orders = umFutures.get_all_orders(symbol=SYMBOL)
            print(open_orders)
            if open_orders != []:
                # 立马下止损单
                for order in open_orders:
                    # 持有订单
                    if order['status'] == 'FILLED':
                        print(f"[{current_time}] 持有订单: {order}")
                        # 获取订单信息
                        order_info = umFutures.query_order(symbol=SYMBOL ,orderId=order['orderId'])
                        print(order_info)
                        # 获取订单价格
                        order_price = order_info['price']
                        # 获取订单数量
                        order_amount = order_info['origQty']

                        strs = json.dumps(order_info, indent=4)
                        wxwork_message(webhook_url, strs)

        except Exception as e:
            print(f"查询失败: {str(e)}")
            wxwork_message(webhook_url, f"查询失败, 检查网络，并手动的币安交易所确认订单状态\n{e}")
        time.sleep(10)