import os
import json
import time
import datetime
from config import TRADES_DB_FILE, MAX_OPEN_POSITIONS, RISK_PER_TRADE_PCT

class TradeManager:
    def __init__(self):
        self.file_path = TRADES_DB_FILE
        self.data = self._load()

    def _load(self):
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "active_trades": {},
            "history": [],
            "stats": {
                "total_trades": 0,
                "wins": 0,
                "full_wins": 0,
                "be_wins": 0,
                "losses": 0,
                "realized_pnl_usdt": 0.0,
                "realized_pnl_r": 0.0
            }
        }

    def _save(self):
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get_open_trades_count(self):
        return len(self.data["active_trades"])

    def can_open_new_trade(self, symbol):
        if len(self.data["active_trades"]) >= MAX_OPEN_POSITIONS:
            return False, f"Maximum open positions reached ({MAX_OPEN_POSITIONS})"
        if symbol in self.data["active_trades"]:
            return False, f"Position already open for {symbol}"
        return True, "OK"

    def open_trade(self, signal, client, telegram):
        symbol = signal["symbol"]
        can_open, reason = self.can_open_new_trade(symbol)
        if not can_open:
            return False, reason

        balance = client.get_usdt_balance()
        if balance < 15.0:
            return False, f"Insufficient USDT balance: {balance}"

        # 8% of equity
        usdt_alloc = balance * RISK_PER_TRADE_PCT
        if usdt_alloc < 10.0:
            usdt_alloc = min(balance * 0.95, 10.0)

        # Place Market Buy
        order, err = client.market_buy(symbol, usdt_alloc)
        if err or not order:
            return False, f"Order error: {err}"

        trade_info = {
            "id": f"{symbol}_{int(time.time())}",
            "symbol": symbol,
            "entry": order["price"],
            "qty_total": order["qty"],
            "qty_remaining": order["qty"],
            "cost": order["cost"],
            "sl": signal["sl"],
            "tp1": signal["tp1"],
            "tp2": signal["tp2"],
            "risk": signal["risk"],
            "pattern": signal["pattern"],
            "tp1_hit": False,
            "entry_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        self.data["active_trades"][symbol] = trade_info
        self._save()

        # Send Telegram alert
        msg = (
            f"🚀 <b>تنفيذ صفقة شراء جديدة (New Long)</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🪙 <b>العملة:</b> #{symbol.replace('USDT', '')}\n"
            f"💵 <b>سعر الدخول:</b> <code>{order['price']}</code>\n"
            f"🎯 <b>الهدف الأول (TP1):</b> <code>{signal['tp1']:.4f}</code> (+1.5R)\n"
            f"🏆 <b>الهدف الثاني (TP2):</b> <code>{signal['tp2']:.4f}</code> (+2.5R)\n"
            f"🛑 <b>وقف الخسارة (SL):</b> <code>{signal['sl']:.4f}</code>\n"
            f"💰 <b>قيمة الصفقة:</b> {order['cost']:.2f} USDT (8% من الحساب)\n"
            f"📊 <b>النموذج:</b> {signal['pattern']}\n"
            f"📈 <b>الصفقات النشطة:</b> {self.get_open_trades_count()}/{MAX_OPEN_POSITIONS}"
        )
        telegram.send_alert(msg)
        return True, "Executed"

    def monitor_positions(self, client, telegram):
        active = list(self.data["active_trades"].values())
        if not active:
            return

        for t in active:
            symbol = t["symbol"]
            curr_price = client.get_ticker_price(symbol)
            if curr_price <= 0:
                continue

            # State 1: Before TP1
            if not t["tp1_hit"]:
                # Check TP1 hit
                if curr_price >= t["tp1"]:
                    half_qty = t["qty_total"] / 2.0
                    order, err = client.market_sell(symbol, half_qty)
                    sold_qty = order["qty"] if order else half_qty
                    
                    t["tp1_hit"] = True
                    t["sl"] = t["entry"] # Move to Breakeven
                    t["qty_remaining"] = max(0, t["qty_remaining"] - sold_qty)
                    self._save()

                    msg = (
                        f"🎯 <b>تحقيق الهدف الأول وتأمين الصفقة!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 <b>العملة:</b> #{symbol.replace('USDT', '')}\n"
                        f"💵 <b>سعر البيع:</b> <code>{curr_price}</code>\n"
                        f"🔒 <b>الإجراء:</b> تم إغلاق 50% من الصفقة ونقل الستوب للدخول (Breakeven).\n"
                        f"🛡️ الصفقة الآن مؤمنة بالكامل وخالية من أي مخاطرة!"
                    )
                    telegram.send_alert(msg)

                # Check SL hit
                elif curr_price <= t["sl"]:
                    client.market_sell(symbol, t["qty_remaining"])
                    t["exit_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    t["exit_price"] = curr_price
                    t["status"] = "LOSS"
                    t["pnl_r"] = -1.0
                    pnl_usdt = (curr_price - t["entry"]) * t["qty_total"]
                    t["pnl_usdt"] = round(pnl_usdt, 2)

                    # Update stats
                    self.data["stats"]["total_trades"] += 1
                    self.data["stats"]["losses"] += 1
                    self.data["stats"]["realized_pnl_usdt"] += round(pnl_usdt, 2)
                    self.data["stats"]["realized_pnl_r"] -= 1.0
                    self.data["history"].append(t)
                    del self.data["active_trades"][symbol]
                    self._save()

                    msg = (
                        f"🛑 <b>إغلاق صفقة عند وقف الخسارة</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 <b>العملة:</b> #{symbol.replace('USDT', '')}\n"
                        f"💵 <b>سعر الخروج:</b> <code>{curr_price}</code>\n"
                        f"📉 <b>النتيجة:</b> -1.0R ({pnl_usdt:.2f} USDT)"
                    )
                    telegram.send_alert(msg)

            # State 2: After TP1 hit, tracking second half
            else:
                # Check TP2 hit
                if curr_price >= t["tp2"]:
                    client.market_sell(symbol, t["qty_remaining"])
                    t["exit_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    t["exit_price"] = curr_price
                    t["status"] = "FULL_WIN"
                    t["pnl_r"] = 2.0
                    pnl_usdt = (0.5 * (t["tp1"] - t["entry"]) + 0.5 * (curr_price - t["entry"])) * t["qty_total"]
                    t["pnl_usdt"] = round(pnl_usdt, 2)

                    self.data["stats"]["total_trades"] += 1
                    self.data["stats"]["wins"] += 1
                    self.data["stats"]["full_wins"] += 1
                    self.data["stats"]["realized_pnl_usdt"] += round(pnl_usdt, 2)
                    self.data["stats"]["realized_pnl_r"] += 2.0
                    self.data["history"].append(t)
                    del self.data["active_trades"][symbol]
                    self._save()

                    msg = (
                        f"🏆 <b>تحقيق الهدف الثاني بالكامل! (FULL WIN)</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 <b>العملة:</b> #{symbol.replace('USDT', '')}\n"
                        f"💵 <b>سعر الخروج:</b> <code>{curr_price}</code>\n"
                        f"🚀 <b>الربح الإجمالي:</b> +2.0R (+{pnl_usdt:.2f} USDT)"
                    )
                    telegram.send_alert(msg)

                # Check Breakeven hit
                elif curr_price <= t["sl"]:
                    client.market_sell(symbol, t["qty_remaining"])
                    t["exit_time"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    t["exit_price"] = curr_price
                    t["status"] = "BE_WIN"
                    t["pnl_r"] = 0.75
                    pnl_usdt = 0.5 * (t["tp1"] - t["entry"]) * t["qty_total"]
                    t["pnl_usdt"] = round(pnl_usdt, 2)

                    self.data["stats"]["total_trades"] += 1
                    self.data["stats"]["wins"] += 1
                    self.data["stats"]["be_wins"] += 1
                    self.data["stats"]["realized_pnl_usdt"] += round(pnl_usdt, 2)
                    self.data["stats"]["realized_pnl_r"] += 0.75
                    self.data["history"].append(t)
                    del self.data["active_trades"][symbol]
                    self._save()

                    msg = (
                        f"🛡️ <b>خروج النصف الثاني على نقطة الدخول (Breakeven)</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"🪙 <b>العملة:</b> #{symbol.replace('USDT', '')}\n"
                        f"💵 <b>سعر الخروج:</b> <code>{curr_price}</code>\n"
                        f"✅ <b>الربح المحفوظ:</b> +0.75R (+{pnl_usdt:.2f} USDT)"
                    )
                    telegram.send_alert(msg)
