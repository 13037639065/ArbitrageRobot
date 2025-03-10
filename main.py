import asyncio
from datetime import datetime
import argparse
import requests
import yaml
import ccxt
from collections import defaultdict
from wsmonitor import SinglePairMonitor
from autotrade import execute_arbitrage, load_exchange

class MultiExchangeArbitrageBot(SinglePairMonitor):
    def __init__(self, config, symbol, exchanges, threshold, webhook_url, limit=1, max_trades=1, dry_run=True):
        super().__init__(symbol, exchanges, threshold, webhook_url)
        self.dry_run = dry_run
        self.start_time = datetime.now()
        self.price_records = defaultdict(lambda: None)
        self.balances = defaultdict(lambda: {'base': 0.0, 'quote': 0.0})
        self.trade_count = 0
        self.total_profit = 0
        self.called = False
        self.trade_lock = asyncio.Lock()
        self.base_amount_max_limit = limit
        self.max_trades = max_trades

        self.exchange_instances = {
            ex: load_exchange(config, ex) for ex in self.exchanges
        }
        
        startup_msg = [
            f"🚀 套利机器人启动",
            f"交易对: {symbol}",
            f"交易所: {', '.join(exchanges)}",
            f"模式: {'模拟交易' if dry_run else '真实交易'}",
            f"单次限额: {limit} {symbol.split('/')[0]}",
            f"最大交易次数: {max_trades}",
            f"启动时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"利差阈值: {threshold:.2f}%"
        ]
        self.send_webhook("\n".join(startup_msg))

    async def show_initial_balances(self):
        """余额检查失败直接退出"""
        base_currency, quote_currency = self.symbol.split('/')
        balance_msg = ["💵 初始余额检查:"]
        
        for exchange in self.exchanges:
            try:
                base_balance = await self.check_balance(exchange, base_currency)
                quote_balance = await self.check_balance(exchange, quote_currency)

                if base_balance is None or quote_balance is None:
                    raise ValueError(f"{exchange} 余额数据异常")

                self.balances[exchange]['base'] = base_balance
                self.balances[exchange]['quote'] = quote_balance
                
                balance_msg.append(
                    f"{exchange.upper()}: \n{base_balance:.4f}\t{base_currency}\n{quote_balance:.4f}\t{quote_currency}"
                )
            except Exception as e:
                error_msg = f"{exchange.upper()}: 余额查询失败 ({str(e)})"
                balance_msg.append(error_msg)
                if self.dry_run:
                    pass
                else:
                    raise RuntimeError(error_msg)
        
        full_msg = "\n".join(balance_msg)
        print(full_msg)
        self.send_webhook(full_msg)

    async def check_balance(self, exchange_name, currency):
        try:
            exchange = self.exchange_instances[exchange_name]
            balance = await asyncio.to_thread(
                exchange.fetch_balance, {'type': 'spot'}
            )
            return balance.get(currency, {}).get('free', 0.0)
        except Exception as e:
            print(f"余额查询失败 [{exchange_name}]: {str(e)}")
            return None
        

    async def find_best_opportunity(self):
        """寻找最佳套利机会（带有效性验证）"""
        valid_prices = {k:v for k,v in self.price_records.items() if v is not None}
        if len(valid_prices) < 2:
            return None, None

        # 寻找最低买入价和最高卖出价
        buy_ex = min(valid_prices, key=valid_prices.get)
        sell_ex = max(valid_prices, key=valid_prices.get)
        min_price = valid_prices[buy_ex]
        max_price = valid_prices[sell_ex]
        
        # 计算价差百分比
        spread = ((max_price - min_price) / min_price) * 100

        # 打印实时状态
        status = [
            f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {self.symbol}",
            *[f"{ex.upper()}: {price:.4f}" for ex, price in valid_prices.items()],
            f"价差百分比: {spread:.4f}%"
        ]
        print("\n".join(status) + "\n" + "-"*40)
        
        if spread >= self.threshold:
            return buy_ex, sell_ex, spread
        return None, None, None


    async def safe_execute_arbitrage(self, buy_ex, sell_ex):
        if not self.is_running:
            return None

        if self.dry_run:
            await asyncio.sleep(5) # 等5秒，模拟滑点
            async with self.lock:
                return {
                    'buy_price': self.price_records[buy_ex],
                    'sell_price': self.price_records[sell_ex],
                    'profit': (self.price_records[sell_ex] - self.price_records[buy_ex]) * 1, # 模拟一个基础货币
                    'symbol': self.symbol
                }
        else:
            try:
                # 计算实际可交易量
                buy_price = self.price_records[buy_ex]
                max_buy = self.balances[buy_ex]['quote'] / buy_price
                max_sell = self.balances[sell_ex]['base']
                
                trade_amount = min(
                    max_buy * 0.9,  # 保留10%余量
                    max_sell,
                    self.base_amount_max_limit
                )

                # 提示即将进行的交易信息
                self.send_webhook("\n".join([
                     f"即将进行的交易信息",
                     f"交易对: {self.symbol}",
                     f"买卖交易所: {buy_ex} -> {sell_ex}",
                     f"买入价：{self.price_records[buy_ex]:.4f}",
                     f"卖出价：{self.price_records[sell_ex]:.4f}",
                     f"{self.symbol.split("/")[0]}交易量：{trade_amount:.4f}",
                     f"{self.symbol.split("/")[0]}可用余额：(买{max_buy:.4f},卖{max_sell:.4f},限{self.base_amount_max_limit:.4f})",
                ]))

                result = execute_arbitrage(
                    self.symbol,
                    self.exchange_instances[buy_ex],
                    self.exchange_instances[sell_ex],
                    trade_amount,
                    self.price_records[buy_ex] * trade_amount if buy_ex == 'bitget' else None, # bitget只能以U计价买入
                )

                # 完成后显示并更新余额
                await self.show_initial_balances()

                return result
            except Exception as e:
                self.send_webhook(f"‼️ 交易执行异常: {str(e)}")
                exit(2)

    def send_webhook(self, message):
        """增强的 webhook 发送方法"""
        try:
            requests.post(
                self.webhook_url,
                json={"msgtype": "text", "text": {"content": message}},
                timeout=3
            )
        except Exception as e:
            print(f"Webhook 发送失败: {str(e)}")

    async def handle_price_update(self, exchange, price):
        if not self.is_running:
            return

        async with self.lock:
            self.price_records[exchange] = float(price)
            opportunity = await self.find_best_opportunity()
            if not opportunity:
                return
            buy_ex, sell_ex, spread = opportunity

        try:
            if buy_ex == None or sell_ex == None or buy_ex == sell_ex:
                return
            
            if self.trade_lock.locked():
                print(f"⏳ 交易进行中: {buy_ex}→{sell_ex}")
                return

            async with self.trade_lock:
                result = await self.safe_execute_arbitrage(buy_ex, sell_ex)
                if result:
                    self.total_profit += result['profit']
                    if not self.dry_run:
                        self.trade_count += 1

                    alert_msg = [
                        f"✅ {'[模拟] ' if self.dry_run else ''}套利信号",
                        f"交易对: {self.symbol}",
                        f"买入: {buy_ex} ({result['buy_price']:.4f})",
                        f"卖出: {sell_ex} ({result['sell_price']:.4f})",
                        f"价差: {((result['sell_price']-result['buy_price']) / result['buy_price'] * 100.0):.2f}%",
                        f"利润: {result['profit']:.4f} {self.symbol.split('/')[1]}",
                        # 如果是实盘输出手续费
                        f"手续费：{0 if self.dry_run else f'{result['buy_fee']}+{result['sell_fee']}={(result['buy_fee']+result['sell_fee']):.4f}'}",
                        f"剩余次数: {self.max_trades - self.trade_count}"
                    ]
                    self.send_webhook("\n".join(alert_msg))

                    if self.trade_count >= self.max_trades:
                        await self.stop("🎯 已达最大交易次数")

        except Exception as e:
            error_msg = [
                "‼️ 交易异常",
                f"交易所: {buy_ex}→{sell_ex}",
                f"错误: {str(e)}",
                f"剩余次数: {self.max_trades - self.trade_count}"
            ]
            self.send_webhook("\n".join(error_msg))
            print(f"Error: {str(e)}")
            # 直接退出，余额不足，断网问题，账号被限制
            exit(1)

    async def stop(self, reason="正常停止"):
        self.is_running = False
        print(f"🛑 停止原因: {reason}")
        self.send_webhook(f"⚠️ 机器人停止: {reason}")
        self.print_summary()

        # 取消task
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task():
                task.cancel()

    def print_summary(self, is_error=False):
        summary = [
            "\n" + "="*40,
            f"{'⚠️ 异常终止' if is_error else '🔚 正常退出'}",
            f"模式: {'模拟交易' if self.dry_run else '真实交易'}",
            f"交易对: {self.symbol}",
            f"交易所: {', '.join(self.exchanges)}",
            f"利差百分比阈值: {self.threshold}%",
            f"运行时长: {datetime.now() - self.start_time}",
            f"总交易次数: {self.trade_count}",
            f"总利润: {self.total_profit:.4f}",
            "="*40
        ]
        report = "\n".join(summary)
        print(report)
        self.send_webhook(report)

async def main():
    parser = argparse.ArgumentParser(description="多交易所套利机器人")
    parser.add_argument('--real-trade', action='store_false', dest='dry_run',
                      help='启用真实交易(默认模拟)')
    parser.add_argument('--config', default='config.yaml', help='配置文件路径')
    parser.add_argument('--symbol', required=True, help='交易对，例如 BTC/USDT')
    parser.add_argument('--exchanges', required=True, nargs='+', 
                       choices=['binance', 'okx', 'bitget', 'htx'],
                       help='监控的交易所列表')
    parser.add_argument('--threshold', type=float, default=0.3, help='价差阈值(百分比)')
    parser.add_argument('--limit', type=float, default=1, help='单次交易限额')
    parser.add_argument('--max-trades', type=int, default=1, help='最大交易次数')
    parser.set_defaults(dry_run=True)
    args = parser.parse_args()

    try:
        with open(args.config) as f:
            config = yaml.safe_load(f)
        bot = MultiExchangeArbitrageBot(
            config=config,
            symbol=args.symbol,
            exchanges=args.exchanges,
            threshold=args.threshold,
            webhook_url=config['webhook'],
            limit=args.limit,
            max_trades=args.max_trades,
            dry_run=args.dry_run
        )
        
        # 先同步初始化
        await bot.show_initial_balances()
        
        # 启动交易所连接
        tasks = [bot.connect_exchange(ex) for ex in args.exchanges]
        await asyncio.gather(*tasks)
    except asyncio.exceptions.CancelledError:
        print("\n安全退出")
    except Exception as e:
        print(f"❌ 致命错误: {str(e)}")
        if 'bot' in locals():
            await bot.stop(f"异常终止: {str(e)}")
            

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n安全退出")