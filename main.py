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
    last_shield_state = None
    last_hourly_alert_time = 0 # will trigger on first cycle

    while True:
        try:
            open_count = tm.get_open_trades_count()
            is_safe, btc_p, btc_ema, btc_ret = screener.check_btc_shield()

            # 1. Alert on Shield State Change
            if last_shield_state is not None and is_safe != last_shield_state:
                if not is_safe:
                    telegram.send_alert(
                        f"🔴 <b>تنبيه أمان: درع البيتكوين تحول للأحمر</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 <b>سعر البيتكوين:</b> <code>${btc_p:,.1f}</code>\n"
                        f"📉 <b>متوسط 4H EMA 50:</b> <code>${btc_ema:,.1f}</code>\n"
                        f"🛡️ <b>الإجراء:</b> تم تجميد فتح صفقات شراء جديدة تلقائياً لحماية المحفظة من نزيف السوق."
                    )
                else:
                    telegram.send_alert(
                        f"🟢 <b>تنبيه إيجابي: درع البيتكوين تحول للأخضر!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 <b>سعر البيتكوين:</b> <code>${btc_p:,.1f}</code>\n"
                        f"📈 <b>متوسط 4H EMA 50:</b> <code>${btc_ema:,.1f}</code>\n"
                        f"🚀 <b>الإجراء:</b> استئناف فحص الـ 72 عملة لاقتناص فرص الشراء الانعكاسية عند الدعوم."
                    )
            last_shield_state = is_safe

            # 2. Hourly Market Pulse (Tells user if no trades opened and WHY)
            now_ts = time.time()
            if now_ts - last_hourly_alert_time >= 3600:
                last_hourly_alert_time = now_ts
                shield_badge = "🟢 آمن للشراء (SAFE)" if is_safe else "🔴 أحمر - تجميد الصفقات (RED)"
                
                if not is_safe:
                    reason_text = (
                        f"⚠️ <b>سبب عدم فتح صفقات:</b>\n"
                        f"البيتكوين يتداول أسفل متوسط 4H EMA 50 (${btc_p:,.1f} أضعف من ${btc_ema:,.1f})، "
                        f"والنظام يحمي محفظتك من الدخول في فخاخ الهبوط."
                    )
                elif open_count >= MAX_OPEN_POSITIONS:
                    reason_text = f"⚠️ <b>سبب عدم فتح صفقات:</b> تم الوصول للحد الأقصى من الصفقات المفتوحة ({MAX_OPEN_POSITIONS}/{MAX_OPEN_POSITIONS})."
                else:
                    reason_text = (
                        f"🔍 <b>سبب عدم فتح صفقات:</b>\n"
                        f"درع البيتكوين آمن، وتم فحص الـ 72 عملة بالكامل؛ لم تتشكل بعد شمعة انعكاسية مكتملة الشروط (ابتلاعية أو سحب سيولة SFP) عند مناطق الدعم."
                    )

                pulse_msg = (
                    f"📢 <b>تقرير الفحص الدوري للسوق (كل ساعة)</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🪙 <b>سعر البيتكوين:</b> <code>${btc_p:,.1f}</code> (تغير: {btc_ret*100:+.2f}%)\n"
                    f"🛡️ <b>حالة درع الحماية:</b> {shield_badge}\n"
                    f"📊 <b>الصفقات النشطة حالياً:</b> {open_count}/{MAX_OPEN_POSITIONS}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"{reason_text}\n"
                    f"💡 <i>السكرينر مستمر في مراقبة الـ 72 عملة لحظة بلحظة في السحاب.</i>"
                )
                telegram.send_alert(pulse_msg)

            # 3. Check open positions capacity
            if open_count >= MAX_OPEN_POSITIONS:
                print(f"[Screener] Max positions reached ({open_count}/{MAX_OPEN_POSITIONS}). Pausing scan.")
                time.sleep(60)
                continue

            # 4. Check BTC Shield for active scanning
            if not is_safe:
                print(f"[Screener] BTC Shield is RED (BTC: {btc_p:.1f} < EMA: {btc_ema:.1f}). Pausing scan.")
                time.sleep(90)
                continue

            print(f"\n[Screener] Scanning 72 coins at {datetime.datetime.now().strftime('%H:%M:%S')} (BTC: ${btc_p:,.0f} - Shield SAFE)...")
            
            # 5. Scan Watchlist
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
                    time.sleep(2)
                else:
                    time.sleep(0.1)

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
