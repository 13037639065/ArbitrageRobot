from hyperliquid.info import Info
from hyperliquid.utils import constants
from typing import Any
import os
import time
import json
from feishu_msg import send_feishu_text
import sys
import datetime
import argparse

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

DIRECTION_MAPPING = {
    "Close Long": "平多",
    "Close Short": "平空",
    "Open Long": "开多", 
    "Open Short": "开空"
}

class TradeMonitor:
    def __init__(self, address):
        self.info = Info(constants.MAINNET_API_URL, skip_ws=False)
        self.subscription_id = None
        self.target_address = address

    def handle_update(self, data: Any):
        try:
            if "data" in data and "fills" in data["data"]:
                fills = data["data"]["fills"]
                for fill in fills:
                    coin = fill.get("coin", "未知币种")
                    value = float(fill.get("px", 0)) * float(fill.get("sz", 0))
                    dt = datetime.datetime.fromtimestamp(fill['time'] / 1000)  # 转换为秒
                    timedate_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    direction = DIRECTION_MAPPING[fill["dir"]]
                    content = f"代币：{coin}\nn方向：{direction}\n成交时间：{timedate_str}\n成交金额：{value:.2f}\n成交价格：{fill['px']}\n成交数量：{fill['sz']}\n"
                    send_feishu_text(WEBHOOK_URL, f"{coin} 交易提醒", content)

        except Exception as e:
            print(f"处理更新时发生错误: {str(e)}")

    def start_monitoring(self):
        try:
            # 订阅用户数据
            self.subscription_id = self.info.subscribe(
                {"type": "userEvents", "user": self.target_address},
                self.handle_update
            )
            print(f"开始监控地址 {self.target_address} 的实时交易...")
            print("按 Ctrl+C 停止监控...")

            # 保持主线程运行
            while True:
                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n监控已停止")
        finally:
            self.stop_monitoring()

    def stop_monitoring(self):
        """停止监控"""
        self.info.disconnect_websocket()
        print("连接已关闭")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="监控指定用户的 Hyperliquid 交易.")
    parser.add_argument("address", type=str, help="要监控的用户地址")
    args = parser.parse_args()

    monitor = TradeMonitor(args.address)
    monitor.start_monitoring()