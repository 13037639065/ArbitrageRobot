import requests
import time
import json
last_notification_time = 0  # 新增频率限制变量
def send_feishu_text(webhook_url, title, content, interval=None):
    global last_notification_time  # 引入全局时间戳

    # 频率限制检查（10秒冷却）
    current_time = time.time()
    if interval != None and current_time - last_notification_time < interval:
        print(f"触发频率限制，跳过通知 {content}")
        return

    headers = {"Content-Type": "application/json"}
    payload = {
        "msg_type": "text",
        "content": content,
        "title": title,
    }
    response = requests.post(webhook_url,  headers=headers, data=json.dumps(payload))
    last_notification_time = current_time
    return response.json()