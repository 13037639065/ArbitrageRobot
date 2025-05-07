import os
import time
import pathlib

from binance.spot import Spot
from configparser import ConfigParser

def get_api_key():
    config = ConfigParser()
    config_file_path = os.path.join(
        pathlib.Path(__file__).parent.resolve(), ".", "config.ini"
    )
    config.read(config_file_path)
    return config["keys"]["api_key"], config["keys"]["api_secret"]


if __name__ == '__main__':
    key,secret = get_api_key()
    client = Spot(api_key=key, api_secret=secret)
    print("===========================")
    while True:
        try:
            # 打印当前时间
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{current_time}] 查询合约订单状态...")
            
            # 查询当前合约持有
            open_orders = client.get_open_orders()
            print(open_orders)

        except Exception as e:
            print(f"查询失败: {str(e)}")
        
        time.sleep(10)