import argparse
import json
import threading
import time
from datetime import datetime

import ccxt
import requests

# 全局变量存储交易所价格数据，结构：{exchange_name: {'prices': {symbol: price}, 'timestamp': ...}}
exchange_prices = {}
exchange_prices_lock = threading.Lock()  # 用于保证线程安全

def send_message(webhook_url, content):
    """发送消息到Webhook"""
    data = {
        "msgtype": "text",
        "text": {"content": content}
    }
    try:
        response = requests.post(webhook_url, json=data)
        return response.json()
    except Exception as e:
        print(f"发送消息失败: {e}")
        return None

def calculate_spread(prices):
    """计算价差百分比"""
    valid_prices = {k: v for k, v in prices.items() if v is not None}
    if len(valid_prices) < 2:
        return 0.0
    max_price = max(valid_prices.values())
    min_price = min(valid_prices.values())
    return ((max_price - min_price) / min_price) * 100

def fetch_exchange_prices_loop(exchange_name, symbols, interval):
    """交易所价格获取循环"""
    exchange = getattr(ccxt, exchange_name)({
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })

    print(f"[{exchange_name}] 启动价格采集，交易对: {', '.join(symbols)}")

    while True:
        try:
            prices = {}
            try:
                # 优先尝试批量获取
                tickers = exchange.fetch_tickers(symbols)
                for symbol in symbols:
                    if symbol in tickers:
                        prices[symbol] = tickers[symbol]['last']
                    else:
                        prices[symbol] = None
            except (ccxt.NotSupported, ccxt.ExchangeError):
                # 回退到逐个获取
                for symbol in symbols:
                    try:
                        ticker = exchange.fetch_ticker(symbol)
                        prices[symbol] = ticker['last'] if ticker['last'] is not None else None
                    except Exception as e:
                        print(f"[{exchange_name} {symbol}] 获取失败: {str(e)}")
                        prices[symbol] = None

            # 更新全局价格数据
            with exchange_prices_lock:
                exchange_prices[exchange_name] = {
                    'prices': prices,
                    'timestamp': time.time()
                }

        except Exception as e:
            print(f"[{exchange_name}] 采集异常: {str(e)}")
            with exchange_prices_lock:
                exchange_prices[exchange_name] = {
                    'prices': {symbol: None for symbol in symbols},
                    'timestamp': time.time()
                }

        time.sleep(interval)

def monitor_symbol_spread(symbol, exchange_names, threshold, interval, webhook_url):
    """单个交易对价差监控"""
    print(f"开始监控 {symbol} (交易所: {', '.join(exchange_names)})")

    while True:
        try:
            prices = {}
            with exchange_prices_lock:
                for name in exchange_names:
                    data = exchange_prices.get(name, {})
                    price = data.get('prices', {}).get(symbol)
                    prices[name] = float(price) if price is not None else None

            current_spread = calculate_spread(prices)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 构建状态信息
            status_msg = [f"[{timestamp}] {symbol} 当前价差: {current_spread:.2f}%"]
            for name, price in prices.items():
                status = f"{price:.2f}" if price is not None else "获取失败"
                status_msg.append(f"{name.upper():<8} | {status}")

            print("\n".join(status_msg) + "\n" + "-"*40)

            # 触发警报条件
            if current_spread >= threshold:
                alert_msg = (
                    f"价差警报！{symbol}\n"
                    f"当前价差: {current_spread:.2f}% (阈值: {threshold}%)\n"
                    f"交易所价格表:\n"
                    f"{json.dumps(prices, indent=4, ensure_ascii=False)}\n"
                )
                print(f"!!! 警报触发: {alert_msg}")
                send_message(webhook_url, alert_msg)

        except Exception as e:
            print(f"[{symbol}] 监控异常: {str(e)}")

        time.sleep(interval)

def main():
    parser = argparse.ArgumentParser(description="多交易所数字货币价差监控工具（优化版）")
    parser.add_argument('--symbols', required=True, nargs='+', help="监控的交易对列表，例如: BTC/USDT ETH/USDT")
    parser.add_argument('--exchanges', required=True, nargs='+', choices=ccxt.exchanges, help="监控的交易所列表，例如: binance okx")
    parser.add_argument('--threshold', type=float, default=0.1, help="触发警报的价差百分比 (默认: 0.1)")
    parser.add_argument('--interval', type=int, default=10, help="价格检查间隔（秒） (默认: 10)")
    parser.add_argument('--webhook', required=True, help="报警通知的(企业微信的群机器人)Webhook URL")

    args = parser.parse_args()

    # 初始化全局数据结构
    with exchange_prices_lock:
        for exchange in args.exchanges:
            exchange_prices[exchange] = {'prices': {}, 'timestamp': 0}

    print(f"\n{'='*40}")
    print(f"启动优化版价差监控系统")
    print(f"交易对: {', '.join(args.symbols)}")
    print(f"交易所: {', '.join(args.exchanges)}")
    print(f"警报阈值: {args.threshold}%")
    print(f"采集间隔: {args.interval}秒")
    print(f"{'='*40}\n")

    # 启动交易所数据采集线程
    exchange_threads = []
    for exchange in args.exchanges:
        thread = threading.Thread(
            target=fetch_exchange_prices_loop,
            args=(exchange, args.symbols, args.interval)
        )
        thread.daemon = True
        thread.start()
        exchange_threads.append(thread)
        print(f"[主程序] 已启动交易所数据线程: {exchange}")

    # 启动交易对监控线程
    symbol_threads = []
    for symbol in args.symbols:
        thread = threading.Thread(
            target=monitor_symbol_spread,
            args=(symbol, args.exchanges, args.threshold, args.interval, args.webhook)
        )
        thread.daemon = True
        thread.start()
        symbol_threads.append(thread)
        print(f"[主程序] 已启动价差监控线程: {symbol}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[主程序] 收到终止信号，正在关闭所有线程...")

if __name__ == "__main__":
    main()