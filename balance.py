import argparse 
import ccxt 
import yaml 
from pathlib import Path 
from decimal import Decimal 
 
def load_config():
    """从 config.yaml  加载交易所 API 配置"""
    config_path = Path(__file__).parent / 'config.yaml' 
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) 
    except FileNotFoundError:
        raise SystemExit("❌ 错误：未找到 config.yaml  文件")
    except Exception as e:
        raise SystemExit(f"❌ 读取配置失败: {e}")
 
def get_spot_balance(exchange_name, symbol=None):
    """查询指定交易所的现货余额"""
    config = load_config()
    try:
        api_key = config[exchange_name]['api_key']
        api_secret = config[exchange_name]['api_secret']
    except KeyError:
        raise SystemExit(f"❌ 交易所 {exchange_name} 未在 config.yaml  中配置")
 
    # 初始化交易所实例 
    try:
        exchange = getattr(ccxt, exchange_name)({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True  # 避免 API 限速 
        })
        balance = exchange.fetch_balance() 
    except ccxt.NetworkError as e:
        raise SystemExit(f"❌ 网络错误: {e}")
    except ccxt.ExchangeError as e:
        raise SystemExit(f"❌ 交易所接口错误: {e}")
    except Exception as e:
        raise SystemExit(f"❌ 未知错误: {e}")
 
    # 处理余额数据 
    if symbol:
        base_currency = symbol.split('/')[0] 
        return {base_currency: balance['total'].get(base_currency, 0)}
    else:
        return {k: v for k, v in balance['total'].items() if v > 0}
 
def format_output(data, verbose=False):
    """格式化输出为可读性更强的文本"""
    if verbose:
        header = "🔍 现货余额详情\n" + "-" * 30 + "\n"
        content = "\n".join([f"{k}: {v:.8f}" if isinstance(v, float) else f"{k}: {v}" for k, v in data.items()]) 
        return header + content + "\n" + "-" * 30 
    else:
        return "\n".join([f"{k}: {v}" for k, v in data.items()]) 
 
def main():
    """命令行入口函数"""
    parser = argparse.ArgumentParser(
        description="查询交易所现货余额 - 当前时间：2025年3月8日 10:55",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter 
    )
    parser.add_argument('exchange',  type=str, help="交易所名称（如 binance、okx）")
    parser.add_argument('-s',  '--symbol', type=str, help="指定交易对（如 BTC/USDT）")
    parser.add_argument('-v',  '--verbose', action='store_true', help="显示详细余额信息")
    args = parser.parse_args() 
 
    try:
        balance_data = get_spot_balance(args.exchange,  args.symbol) 
        output = format_output(balance_data, args.verbose) 
        print(output)
    except Exception as e:
        print(e)
 
if __name__ == "__main__":
    main()