from hyperliquid.info import Info
from hyperliquid.utils import constants
from typing import Any
import os
import time
from feishu_msg import send_feishu_text
import sys

# 配置参数
TARGET_ADDRESS = "0x5b5d51203a0f9079f8aeb098a6523a13f298c060"  # 监控地址

# WEBHOOK_URL 从 环境变量获取
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
POSITION_THRESHOLD = 50000  # 加仓价值阈值（单位：美元）
CHECK_INTERVAL = 300  # 状态检查间隔（秒）

class HyperliquidMonitor:
    def __init__(self, address=None):
        self.info = Info(constants.MAINNET_API_URL, skip_ws=False)
        self.subscription_id = None
        self.last_notification_time = 0
        self.last_position_value = 0
        self.target_address = address or TARGET_ADDRESS  # 使用传入地址或默认地址
        send_feishu_text(WEBHOOK_URL, f"启动监控巨鲸 {self.target_address}", "")
    
    def handle_update(self, data: Any):
        try:
            # 提取持仓信息
            if "data" in data and "position" in data["data"]:
                position = data["data"]["position"]
                coin = position.get("coin", "未知币种")
                entry_px = float(position.get("entryPx", 0))
                leverage = position.get("leverage", {}).get("value", 0)
                liquidation_px = position.get("liquidationPx", "无")
                margin_used = float(position.get("marginUsed", 0))
                position_sz = float(position.get("positionSz", 0))
                
                # 计算仓位价值
                position_value = position_sz * entry_px
                
                print(f"\n=== {coin} 持仓更新 ===")
                print(f"币种: {coin}")
                print(f"入场价: ${entry_px:.2f}")
                print(f"杠杆: {leverage}x")
                print(f"保证金使用: ${margin_used:.2f}")
                print(f"仓位数量: {position_sz}")
                print(f"仓位价值: ${position_value:.2f}")
                print(f"清算价格: {liquidation_px}")
                
                # 清仓检测
                if position_sz == 0 and self.last_position_value > 0:
                    print("检测到清仓操作！")
                    msg = f"【Hyperliquid 清仓通知】\n地址: {TARGET_ADDRESS}\n币种: {coin}\n仓位价值: ${self.last_position_value:.2f}"
                    send_feishu_text(WEBHOOK_URL, "Hyperliquid 清仓通知", msg)
                
                # 大额加仓检测
                position_change = position_value - self.last_position_value
                if position_change > POSITION_THRESHOLD:
                    print(f"检测到大额加仓！价值: ${position_change:.2f}")
                    msg = f"【Hyperliquid 大额加仓通知】\n地址: {TARGET_ADDRESS}\n币种: {coin}\n加仓价值: ${position_change:.2f}\n总仓位价值: ${position_value:.2f}"
                    send_feishu_text(WEBHOOK_URL, "Hyperliquid 大额加仓通知", msg)
                
                self.last_position_value = position_value
                
            # 提取成交信息
            elif "data" in data and "fills" in data["data"]:
                fills = data["data"]["fills"]
                for fill in fills:
                    coin = fill.get("coin", "未知币种")
                    px = float(fill.get("px", 0))
                    sz = float(fill.get("sz", 0))
                    side = fill.get("type", "未知方向")
                    time_ms = int(fill.get("time", 0))
                    timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time_ms / 1000))
                    
                    # 计算成交价值
                    trade_value = abs(sz) * px
                    
                    print(f"\n=== 新成交 {timestamp} ===")
                    print(f"币种: {coin}")
                    print(f"价格: ${px:.2f}")
                    print(f"数量: {sz}")
                    print(f"方向: {side}")
                    print(f"成交价值: ${trade_value:.2f}")
                    
                    # 大额交易提醒
                    if trade_value > POSITION_THRESHOLD:
                        print("检测到大额交易！")
                        msg = f"【Hyperliquid 大额交易通知】\n地址: {TARGET_ADDRESS}\n币种: {coin}\n方向: {side}\n价格: ${px:.2f}\n数量: {sz}\n成交价值: ${trade_value:.2f}"
                        send_feishu_text(WEBHOOK_URL, "Hyperliquid 大额交易通知", msg)

        except Exception as e:
            print(f"处理更新时发生错误: {str(e)}")

    def start_monitoring(self):
        try:
            # 订阅用户数据
            self.subscription_id = self.info.subscribe(
                {"type": "user", "user": TARGET_ADDRESS},
                self.handle_update
            )
            
            print(f"开始监控地址 {TARGET_ADDRESS} 的实时交易...")
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
            user_state = self.info.user_state(TARGET_ADDRESS)
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
            
            if "assetPositions" in user_state:
                for asset in user_state["assetPositions"]:
                    position = asset.get("position", {})
                    coin = position.get("coin", "未知币种")
                    position_sz = float(position.get("positionSz", 0))
                    entry_px = float(position.get("entryPx", 0))
                    
                    if position_sz != 0:
                        position_value = position_sz * entry_px
                        print(f"\n{coin} 持仓:")
                        print(f"数量: {position_sz}")
                        print(f"入场价: ${entry_px:.2f}")
                        print(f"价值: ${position_value:.2f}")
                        
                        # 检测大额持仓
                        if position_value > POSITION_THRESHOLD:
                            msg = f"【Hyperliquid 大额持仓提醒】\n地址: {TARGET_ADDRESS}\n币种: {coin}\n价值: ${position_value:.2f}\n入场价: ${entry_px:.2f}\n数量: {position_sz}" 
                            send_feishu_text(WEBHOOK_URL, "Hyperliquid 大额持仓提醒", msg)
            
            return total_ntl_pos
            
        except Exception as e:
            print(f"获取账户状态时发生错误: {str(e)}")
            return 0
    
    def detect_position_changes(self, current_position_value):
        """检测仓位变化"""
        position_change = current_position_value - self.last_position_value
        if position_change > POSITION_THRESHOLD:
            print(f"检测到大额加仓！价值: ${position_change:.2f}")
            msg = f"【Hyperliquid 大额加仓通知】\n地址: {TARGET_ADDRESS}\n加仓价值: ${position_change:.2f}\n总仓位价值: ${current_position_value:.2f}"
            send_feishu_text(WEBHOOK_URL, "Hyperliquid 大额加仓通知", msg)
        
        self.last_position_value = current_position_value
    
    def stop_monitoring(self):
        """停止监控"""
        if self.subscription_id is not None:
            self.info.unsubscribe(self.subscription_id)
            print("订阅已取消")
        self.info.disconnect_websocket()
        print("连接已关闭")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_address = sys.argv[1]
        monitor = HyperliquidMonitor(target_address)
    else:
        monitor = HyperliquidMonitor()
    monitor.start_monitoring()