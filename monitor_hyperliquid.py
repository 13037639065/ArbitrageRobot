from hyperliquid.info import Info
from hyperliquid.utils import constants
from typing import Any
import os
import time
import json
from feishu_msg import send_feishu_text
import sys
import datetime

# 配置参数
DEFAULT_TARGET_ADDRESS = "0x5b5d51203a0f9079f8aeb098a6523a13f298c060"  # 监控地址

# WEBHOOK_URL 从 环境变量获取
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
POSITION_THRESHOLD = 100000  # 加仓价值阈值（单位：美元）
CHECK_INTERVAL = 300  # 状态检查间隔（秒）
WHITE_LIST = ['BTC', 'ETH', 'SUI', 'SOL', "DOGE", "XRP"]
VALUE_FILTER = 10000

DIRECTION_MAPPING = {
    "Close Long": "平多",
    "Close Short": "平空",
    "Open Long": "开多", 
    "Open Short": "开空"
}

class HyperliquidMonitor:
    def __init__(self, address=None):
        self.info = Info(constants.MAINNET_API_URL, skip_ws=False)
        self.subscription_id = None
        self.last_notification_time = 0
        self.last_position_value = 0
        self.target_address = DEFAULT_TARGET_ADDRESS
        if  address != None:
            self.target_address = address
    
    def handle_update(self, data: Any):
        try:
            if "data" in data and "fills" in data["data"]:
                fills = data["data"]["fills"]
                for fill in fills:
                    coin = fill.get("coin", "未知币种")
                    vaule = float(fill.get("px", 0)) * float(fill.get("sz", 0))
                    print(json.dumps(fill, indent=4))
                    if coin in WHITE_LIST and vaule > VALUE_FILTER:
                        print('满足')
                        dt = datetime.datetime.fromtimestamp(fill['time'] / 1000)  # 转换为秒
                        timedate_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                        dir = DIRECTION_MAPPING[fill["dir"]]
                        send_feishu_text(WEBHOOK_URL, f"{coin} 价值：{vaule} 操作：{dir}", f"时间：{timedate_str}\n地址：{self.target_address}\n{json.dumps(fill, indent=4)}")
                    else:
                        print('条件不满足')
                        
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
            print(f"大额交易阈值: ${POSITION_THRESHOLD:.2f}")
            print("按 Ctrl+C 停止监控...")
            
            # 定期检查持仓状态
            while True:
                current_position_value = self.check_position_status()
                self.detect_position_changes(current_position_value)
                time.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n监控已停止")
        finally:
            self.stop_monitoring()
    
    def check_position_status(self):
        """获取并显示当前持仓状态"""
        try:
            user_state = self.info.user_state(self.target_address)
            cross_margin_summary = user_state.get("crossMarginSummary", {})
            account_value = float(cross_margin_summary.get("accountValue", 0))
            total_raw_usd = float(cross_margin_summary.get("totalRawUsd", 0))
            total_ntl_pos = float(cross_margin_summary.get("totalNtlPos", 0))
            withdrawable = float(cross_margin_summary.get("withdrawable", 0))
            
            print("\n=== 账户状态 ===")
            print(f"账户净值: ${account_value:.2f}")
            print(f"总资产价值: ${total_raw_usd:.2f}")
            print(f"总名义头寸: ${total_ntl_pos:.2f}")
            print(f"可提取金额: ${withdrawable:.2f}")
            
            # 记录总仓位价值
            total_position_value = 0
            
            if "assetPositions" in user_state:
                for asset in user_state["assetPositions"]:
                    position = asset.get("position", {})
                    coin = position.get("coin", "未知币种")
                    position_sz = float(position.get("szi", 0))  # 使用szi字段作为持仓数量
                    entry_px = float(position.get("entryPx", 0))
                    
                    if position_sz != 0:
                        position_value = abs(position_sz) * entry_px
                        total_position_value += position_value
                        
                        print(f"\n{coin} 持仓:")
                        print(f"数量: {position_sz}")
                        print(f"入场价: ${entry_px:.2f}")
                        print(f"价值: ${position_value:.2f}")
                        
                        # 检测大额持仓
                        if position_value > POSITION_THRESHOLD:
                            msg = f"【Hyperliquid 大额持仓提醒】\n地址: {self.target_address}\n币种: {coin}\n价值: ${position_value:.2f}\n入场价: ${entry_px:.2f}\n数量: {position_sz}" 
                            send_feishu_text(WEBHOOK_URL, "Hyperliquid 大额持仓提醒", msg)
            
            return total_position_value  # 返回计算的总仓位价值
            
        except Exception as e:
            print(f"获取账户状态时发生错误: {str(e)}")
            return self.last_position_value  # 出错时返回最后已知值
    
    def detect_position_changes(self, current_position_value):
        """检测仓位变化"""
        position_change = current_position_value - self.last_position_value
        
        print(f"\n=== 仓位变化检测 ===")
        print(f"当前仓位价值: ${current_position_value:.2f}")
        print(f"上次仓位价值: ${self.last_position_value:.2f}")
        print(f"变化值: ${position_change:.2f}")
        
        # 清仓检测（当仓位从非零变为零）
        if self.last_position_value > 0 and current_position_value == 0:
            print("检测到清仓操作！")
            msg = f"【Hyperliquid 清仓通知】\n地址: {self.target_address}\n总交易价值: ${self.last_position_value:.2f}"
            send_feishu_text(WEBHOOK_URL, "Hyperliquid 清仓通知", msg)
        
        # 大额加仓检测（当变化值超过阈值）
        elif position_change > POSITION_THRESHOLD:
            print(f"检测到大额加仓！价值: ${position_change:.2f}")
            msg = f"【Hyperliquid 大额加仓通知】\n地址: {self.target_address}\n加仓价值: ${position_change:.2f}\n总仓位价值: ${current_position_value:.2f}"
            send_feishu_text(WEBHOOK_URL, "Hyperliquid 大额加仓通知", msg)
        
        # 更新最后仓位值
        self.last_position_value = current_position_value
    
    def stop_monitoring(self):
        """停止监控"""
        self.info.disconnect_websocket()
        print("连接已关闭")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_address = sys.argv[1]
        monitor = HyperliquidMonitor(target_address)
    else:
        monitor = HyperliquidMonitor()
    monitor.start_monitoring()