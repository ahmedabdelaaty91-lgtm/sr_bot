import time
import threading
import datetime
import traceback
from config import WATCHLIST_PAIRS, MAX_OPEN_POSITIONS
from binance_client import BinanceClient
from trade_manager import TradeManager
import strategy_screener as screener
from telegram_service import TelegramService

print("=" * 60)
print("STARTING BINANCE SPOT VIRTUAL TRADING ENGINE (72 COINS)")
print("=" * 60)

client = BinanceClient()
tm = TradeManager()
telegram = TelegramService(client, tm, screener)

balance = client.get_usdt_balance()
print(f"Connected to Binance Testnet. USDT Balance: {balance:.2f} USDT")
print(f"Max Open Positions: {MAX_OPEN_POSITIONS} | Position Size: 8% per trade")
print(f"Active Trades currently open: {tm.get_open_trades_count()}")

def position_monitor_worker():
    print("[Worker] Position Monitor started (interval: 15s)...")
    while True:
        try:
            tm.monitor_positions(client, telegram)
        except Exception as e:
            print(f"[Monitor Error]: {e}")
        time.sleep(15)

def telegram_poll_worker():
    print("[Worker] Telegram Poller started...")
    while True:
        try:
            telegram.poll_updates()
        except Exception as e:
            print(f"[Telegram Poll Error]: {e}")
        time.sleep(1.5)

def screener_worker():
    print("[Worker] Screener started (scanning 72 pairs)...")
    while True:
        try:
            # 1. Check open positions capacity
            open_count = tm.get_open_trades_count()
            if open_count >= MAX_OPEN_POSITIONS:
                print(f"[Screener] Max positions reached ({open_count}/{MAX_OPEN_POSITIONS}). Pausing scan.")
                time.sleep(60)
                continue

            # 2. Check BTC Shield
            is_safe, btc_p, btc_ema, btc_ret = screener.check_btc_shield()
            if not is_safe:
                print(f"[Screener] BTC Shield is RED (BTC: {btc_p:.1f} < EMA: {btc_ema:.1f}). Pausing scan.")
                time.sleep(90)
                continue

            print(f"\n[Screener] Scanning 72 coins at {datetime.datetime.now().strftime('%H:%M:%S')} (BTC: ${btc_p:,.0f} - Shield SAFE)...")
            
            # 3. Scan Watchlist
            for pair in WATCHLIST_PAIRS:
                if tm.get_open_trades_count() >= MAX_OPEN_POSITIONS:
                    break
                if pair in tm.data["active_trades"]:
                    continue

                signal = screener.check_symbol_setup(pair)
                if signal:
                    print(f"===> SIGNAL DETECTED: {pair} ({signal['pattern']}) Entry: {signal['entry']}")
                    success, msg = tm.open_trade(signal, client, telegram)
                    print(f"Execution result: {success} - {msg}")
                    time.sleep(2) # brief pause after executing
                else:
                    time.sleep(0.1) # rate limit friendly

            # Scan completed, wait 2 minutes before next scan cycle
            print(f"[Screener] Scan cycle finished. Active trades: {tm.get_open_trades_count()}/{MAX_OPEN_POSITIONS}")
            time.sleep(120)

        except Exception as e:
            print(f"[Screener Loop Error]: {e}")
            traceback.print_exc()
            time.sleep(30)

def main():
    t_monitor = threading.Thread(target=position_monitor_worker, daemon=True)
    t_telegram = threading.Thread(target=telegram_poll_worker, daemon=True)
    t_screener = threading.Thread(target=screener_worker, daemon=True)

    t_monitor.start()
    t_telegram.start()
    t_screener.start()

    print("All workers running. Bot is ready.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down bot...")

if __name__ == "__main__":
    main()
