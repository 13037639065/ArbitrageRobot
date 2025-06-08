from hyperliquid.info import Info
from hyperliquid.utils import constants
import json
from typing import Any

# 替换为你要监控的地址
TARGET_ADDRESS = "0x5b5d51203a0f9079f8aeb098a6523a13f298c060"

# 初始化带WebSocket连接的Info实例
info = Info(constants.MAINNET_API_URL, skip_ws=False)
subscription_id = None
# 定义回调函数
def handle_update(data: Any):
    print("\n=== 交易更新 ===")
    print(json.dumps(data, indent=4, ensure_ascii=False))

try:
    # 订阅指定地址的交易数据（新版SDK需要回调函数）
    subscription_id = info.subscribe(
        {"type": "userEvents", "user": TARGET_ADDRESS},  # 订阅参数
        handle_update  # 必须的回调函数
    )
    
    print(f"开始监控地址 {TARGET_ADDRESS} 的实时交易...")
    print("按 Ctrl+C 停止监控...")
    
    # 保持主线程运行（重要！）
    while True:
        pass
        
except KeyboardInterrupt:
    print("\n监控已停止")
finally:
    # 关闭 subscribe 连接
    info.disconnect_websocket()