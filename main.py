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
    def __init__(self, config, symbol, exchanges, threshold, webhook_url, dry_run=True):
        super().__init__(symbol, exchanges, threshold, webhook_url)
        self.dry_run = dry_run  # 新增 dry-run 模式开关
        self.start_time = datetime.now()
        self.price_records = defaultdict(lambda: None)
        self.balances = defaultdict(lambda: {'base': 0.0, 'quote': 0.0})
        self.trade_count = 0
        self.total_profit = 0
        self.called = False

        # 实例化
        self.exchange_instances = {
            ex: load_exchange(config, ex) for ex in self.exchanges
        }
        
        # 初始化时发送启动通知
        startup_msg = [
            f"🚀 套利机器人启动",
            f"交易对: {symbol}",
            f"交易所: {', '.join(exchanges)}",
            f"模式: {'模拟交易' if dry_run else '真实交易'}",
            f"启动时间: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"利差阈值: {threshold:.2f}%"
        ]
        self.send_webhook("\n".join(startup_msg))

        asyncio.create_task(self.show_initial_balances())

    async def show_initial_balances(self):
        """显示初始余额（基础货币和计价货币）"""
        # 解析交易对符号
        base_currency, quote_currency = self.symbol.split('/')  # 拆分为基础货币和计价货币
        
        balance_msg = ["💵 初始余额检查:"]
        
        for exchange in self.exchanges:
            try:
                # 查询两种货币的余额
                base_balance = await self.check_balance(exchange, base_currency)
                quote_balance = await self.check_balance(exchange, quote_currency)

                self.balances[exchange]['base'] = base_balance
                self.balances[exchange]['quote'] = quote_balance
                
                balance_msg.append(
                    f"{exchange.upper()}: \n{base_balance:.4f}\t{base_currency}\n{quote_balance:.4f}\t{quote_currency}"
                )
            except Exception as e:
                balance_msg.append(f"{exchange.upper()}: 查询失败 ({str(e)})")
        
        # 发送到webhook并打印
        full_msg = "\n".join(balance_msg)
        print(full_msg)
        self.send_webhook(full_msg)

    async def check_balance(self, exchange_name, quote_currency):
        """检查指定交易所的计价货币余额"""
        try:
            # 获取交易所实例
            exchange: ccxt.Exchange = self.exchange_instances[exchange_name]
            
            # 调用统一余额接口
            balance = await asyncio.to_thread(
                exchange.fetch_balance,
                {'type': 'spot'}
            )
            
            # 提取指定币种余额
            return balance.get(quote_currency, {}).get('free', 0.0)
            
        except Exception as e:
            print(f"余额查询失败 [{exchange_name}]: {str(e)}")
            return 0.0

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
        """安全执行套利交易（支持模拟模式）"""        
        if self.dry_run:
            trade_amount = 1
        else:
            # 实盘交易
            available_balance = self.balances[sell_ex]['quote']
        
            # 计算动态交易量（可用余额的5%-20%）
            risk_factor = min((self.threshold / 0.3), 0.2)  # 阈值每0.1%对应约6.6%仓位
            trade_amount = min(
                available_balance * risk_factor,
                self.balances[buy_ex]['base']  # 不超过买入交易所的基础货币余额
            )

        print(f"{'[模拟] ' if self.dry_run else ''}执行套利: {buy_ex}→{sell_ex} 数量: {trade_amount:.4f}")
        
        if self.dry_run:
            # 生成模拟交易结果
            return {
                'buy_price': self.price_records[buy_ex],
                'sell_price': self.price_records[sell_ex],
                'profit': (self.price_records[sell_ex] - self.price_records[buy_ex]) * trade_amount,
                'symbol': self.symbol
            }
        else:
            trade_amount = 1
            return execute_arbitrage(
                self.symbol,
                self.exchange_instances[buy_ex],
                self.exchange_instances[sell_ex],
                trade_amount
            )

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
        
        async with self.lock:
            self.price_records[exchange] = float(price)
            buy_ex, sell_ex, spread = await self.find_best_opportunity()
            if not buy_ex or not sell_ex:
                return
            try:
                result = await self.safe_execute_arbitrage(buy_ex, sell_ex)
                if result:
                    self.total_profit += result['profit']
                    self.trade_count += 1
                    
                    alert_msg = (
                        f"✅ {'[模拟] ' if self.dry_run else ''}套利信号\n"
                        f"交易对: {self.symbol}\n"
                        f"买入: {buy_ex} ({result['buy_price']:.4f})\n"
                        f"卖出: {sell_ex} ({result['sell_price']:.4f})\n"
                        f"价差百分比：{spread}%%\n",
                        f"预期利润: {result['profit']:.4f} {self.symbol.split('/')[1]}\n",
                        # 如果是实盘交易显示fee
                        f"手续费：{"0" if self.dry_run else f"({result['buy_fee']}, {result['sell_fee']})"}\n",
                    )
                    self.send_webhook(alert_msg)
            except Exception as e:
                error_msg = [
                    "‼️ 交易执行异常",
                    f"时间: {datetime.now().isoformat()}",
                    f"模式: {'模拟' if self.dry_run else '真实'}",
                    f"错误类型: {type(e).__name__}",
                    f"错误详情: {str(e)}"
                ]
                self.send_webhook("\n".join(error_msg))
                raise

    def print_summary(self, is_error=False):
        """增强的总结报告"""
        self.called = True
        summary = [
            "\n" + "="*40,
            f"{'⚠️ 异常终止' if is_error else '🔚 正常退出'}",
            f"模式: {'模拟交易' if self.dry_run else '真实交易'}",
            f"运行时长: {datetime.now() - self.start_time}",
            f"总交易次数: {self.trade_count}",
            f"总利润: {self.total_profit:.4f}",
            "="*40
        ]
        report = "\n".join(summary)
        print(report)
        self.send_webhook(report)

async def main():
    parser = argparse.ArgumentParser(description="多交易所智能套利机器人")
    # 新增 real-trade 参数（默认保持 dry-run 模式）
    parser.add_argument('--real-trade', action='store_false', dest='dry_run',
                       help='启用真实交易模式（默认是模拟模式）')
    # 修改原有参数定义
    parser.add_argument('--config', default='config.yaml', help='配置文件路径')
    parser.add_argument('--symbol', required=True, help='交易对，例如 BTC/USDT')
    parser.add_argument('--exchanges', required=True, nargs='+', 
                       choices=['binance', 'okx', 'bitget', 'htx'],
                       help='监控的交易所列表')
    parser.add_argument('--threshold', type=float, default=0.3,
                       help='触发套利的最小价差百分比')
    
    # 设置 dry_run 默认值为 True
    parser.set_defaults(dry_run=True)
    
    args = parser.parse_args()

    # 初始化部分
    try:
        with open(args.config) as f:
            config = yaml.safe_load(f)
        webhook_url = config['webhook']
    except FileNotFoundError:
        print(f"错误：配置文件 {args.config} 未找到")
        return

    bot = MultiExchangeArbitrageBot(
        config=config,
        symbol=args.symbol,
        exchanges=args.exchanges,
        threshold=args.threshold,
        webhook_url=webhook_url,
        dry_run=args.dry_run  # 传递 dry-run 参数
    )

    try:
        tasks = [bot.connect_exchange(ex) for ex in args.exchanges]
        await asyncio.gather(*tasks)
    except Exception as e:
        print(e)
    finally:
        bot.print_summary()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序已安全退出")