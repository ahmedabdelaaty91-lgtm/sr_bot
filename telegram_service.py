import os
import json
import time
import requests
import datetime
from config import TELEGRAM_BOT_TOKEN, AUTH_ADMIN_FILE, MAX_OPEN_POSITIONS, TRIAL_DAYS, START_DATE

class TelegramService:
    def __init__(self, binance_client, trade_manager, screener_module):
        self.token = TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.client = binance_client
        self.tm = trade_manager
        self.screener = screener_module
        self.admin_chat_id = self._load_admin()
        self.last_update_id = 0

    def _load_admin(self):
        if os.path.exists(AUTH_ADMIN_FILE):
            try:
                with open(AUTH_ADMIN_FILE, "r") as f:
                    data = json.load(f)
                    return data.get("admin_chat_id", 7760401819)
            except Exception:
                pass
        return 7760401819 # Default Admin (Ahmed Abdelaaty)

    def _save_admin(self, chat_id, user_info):
        self.admin_chat_id = chat_id
        with open(AUTH_ADMIN_FILE, "w") as f:
            json.dump({
                "admin_chat_id": chat_id,
                "user_info": user_info,
                "registered_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, f, indent=2)

    def send_message(self, chat_id, text):
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            r = requests.post(url, json=payload, timeout=5)
            if r.status_code != 200:
                # Fallback to plain text if HTML parsing failed
                payload["parse_mode"] = None
                requests.post(url, json=payload, timeout=5)
        except Exception as e:
            print(f"Error sending telegram message: {e}")

    def send_alert(self, text):
        if self.admin_chat_id:
            self.send_message(self.admin_chat_id, text)

    def poll_updates(self):
        try:
            url = f"{self.base_url}/getUpdates"
            params = {"offset": self.last_update_id + 1, "timeout": 10}
            r = requests.get(url, params=params, timeout=15)
            data = r.json()
            if not data.get("ok"):
                return
            for update in data.get("result", []):
                self.last_update_id = update["update_id"]
                msg = update.get("message")
                if not msg or "text" not in msg:
                    continue
                self._handle_message(msg)
        except Exception as e:
            # Poll timeout or network glitch
            pass

    def _handle_message(self, msg):
        chat_id = msg["chat"]["id"]
        text = msg["text"].strip()
        user_info = msg.get("from", {})

        # Security Registration / Pairing
        if text.startswith("/start"):
            if not self.admin_chat_id:
                self._save_admin(chat_id, user_info)
                welcome = (
                    "🔐 <b>تم تفعيل وتأمين بوت التداول بنجاح!</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>المشرف المعتمد:</b> {user_info.get('first_name', 'Admin')}\n"
                    f"🆔 <b>Chat ID:</b> <code>{chat_id}</code>\n"
                    "🛡️ <b>حالة الأمان:</b> تم قفل البوت على هذا الحساب فقط ولن يستجيب لأي شخص آخر.\n\n"
                    "🤖 <b>نظام التداول التجريبي شغال الآن على باينانس:</b>\n"
                    "• سلة الـ 72 عملة على فريم 1H.\n"
                    "• 8% من رأس المال لكل صفقة (بحد أقصى 11 صفقة).\n"
                    "• تجربة لمدة 15 يوماً.\n\n"
                    "📋 <b>الأوامر المتاحة:</b>\n"
                    "🔹 اكتب <code>صفقات</code> لمعرفة الصفقات المفتوحة وحالتها.\n"
                    "🔹 اكتب <code>تقرير</code> لمعرفة حالة الرصيد والأرباح.\n"
                    "🔹 اكتب <code>رادار</code> لمعرفة وضع السوق والبيتكوين."
                )
                self.send_message(chat_id, welcome)
                return
            elif self.admin_chat_id == chat_id:
                self.send_message(chat_id, "مرحباً بك مجدداً! النظام يعمل بكامل طاقته. أرسل (صفقات، تقرير، رادار).")
                return

        # Security Check
        if self.admin_chat_id and chat_id != self.admin_chat_id:
            self.send_message(chat_id, "⛔ <b>عذراً، هذا البوت مقفل ومخصص لحساب تداول شخصي فقط.</b>")
            return

        # Handle Commands
        cmd = text.lower()
        if cmd in ("صفقات", "/trades", "الصفقات"):
            self._reply_trades(chat_id)
        elif cmd in ("تقرير", "/report", "الحساب"):
            self._reply_report(chat_id)
        elif cmd in ("رادار", "/radar", "السوق"):
            self._reply_radar(chat_id)
        elif cmd in ("مساعدة", "/help"):
            help_msg = (
                "📋 <b>دليل أوامر البوت:</b>\n"
                "• <code>صفقات</code> : عرض جميع الصفقات المفتوحة حالياً وأسعارها والربح اللحظي.\n"
                "• <code>تقرير</code> : كشف حساب تفصيلي للرصيد ونسبة الفوز والأرباح الصافية.\n"
                "• <code>رادار</code> : فحص درع البيتكوين ومسار السوق ومؤشر الأمان."
            )
            self.send_message(chat_id, help_msg)

    def _reply_trades(self, chat_id):
        active = self.tm.data["active_trades"]
        if not active:
            self.send_message(chat_id, "📭 <b>لا توجد صفقات مفتوحة حالياً.</b>\nالسكرينر يفحص سلة الـ 72 عملة بانتظار تشكل فرص جديدة.")
            return

        lines = [f"📊 <b>الصفقات المفتوحة حالياً ({len(active)}/{MAX_OPEN_POSITIONS}):</b>\n━━━━━━━━━━━━━━━━━━"]
        for sym, t in active.items():
            curr = self.client.get_ticker_price(sym)
            pnl_pct = ((curr - t["entry"]) / t["entry"]) * 100 if curr > 0 else 0
            emoji = "🟢" if pnl_pct >= 0 else "🔴"
            status_text = "🛡️ مؤمنة على الدخول" if t["tp1_hit"] else "⏳ بانتظار الهدف 1"
            lines.append(
                f"{emoji} <b>#{sym.replace('USDT', '')}</b>\n"
                f"• الدخول: <code>{t['entry']}</code> | الحالي: <code>{curr}</code> ({pnl_pct:+.2f}%)\n"
                f"• TP1: <code>{t['tp1']:.4f}</code> | TP2: <code>{t['tp2']:.4f}</code>\n"
                f"• SL: <code>{t['sl']:.4f}</code> | الحالة: {status_text}\n"
            )
        self.send_message(chat_id, "\n".join(lines))

    def _reply_report(self, chat_id):
        stats = self.tm.data["stats"]
        usdt_free = self.client.get_usdt_balance()
        
        # Calculate active trades locked equity
        active_cost = sum(t["cost"] for t in self.tm.data["active_trades"].values())
        total_equity = usdt_free + active_cost

        # Trial day calculation
        start_dt = datetime.datetime.strptime(START_DATE, "%Y-%m-%d")
        days_passed = (datetime.datetime.now() - start_dt).days + 1
        days_passed = max(1, min(days_passed, TRIAL_DAYS))

        total_completed = stats["total_trades"]
        wr = (stats["wins"] / total_completed * 100) if total_completed > 0 else 0

        report = (
            f"📈 <b>تقرير الأداء وحساب باينانس الافتراضي</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🗓️ <b>فترة التجربة:</b> اليوم {days_passed} من {TRIAL_DAYS}\n"
            f"💵 <b>رصيد USDT المتاح:</b> <code>{usdt_free:.2f} $</code>\n"
            f"💼 <b>إجمالي قيمة المحفظة:</b> <code>{total_equity:.2f} $</code>\n"
            f"📊 <b>الصفقات النشطة:</b> {len(self.tm.data['active_trades'])} / {MAX_OPEN_POSITIONS}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>إجمالي الصفقات المكتملة:</b> {total_completed}\n"
            f"🏆 <b>أهداف كاملة (TP2):</b> {stats['full_wins']}\n"
            f"🛡️ <b>خروج بربح على الدخول (BE):</b> {stats['be_wins']}\n"
            f"🛑 <b>صفقات خاسرة:</b> {stats['losses']}\n"
            f"🎯 <b>نسبة الفوز (Win Rate):</b> <b>{wr:.1f}%</b>\n"
            f"💰 <b>صافي الأرباح المحققة:</b> <b>{stats['realized_pnl_usdt']:+.2f} USDT</b> ({stats['realized_pnl_r']:+.2f} R)"
        )
        self.send_message(chat_id, report)

    def _reply_radar(self, chat_id):
        is_safe, btc_price, btc_ema, btc_ret = self.screener.check_btc_shield()
        status_badge = "🟢 <b>الدرع أخضر (مسموح بالدخول)</b>" if is_safe else "🔴 <b>الدرع أحمر (ممنوع الدخول - السوق هابط)</b>"
        
        radar_msg = (
            f"📡 <b>رادار السوق ودرع البيتكوين اللحظي</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🪙 <b>سعر البيتكوين:</b> <code>{btc_price:,.2f} $</code>\n"
            f"📉 <b>متوسط 4H EMA 50:</b> <code>{btc_ema:,.2f} $</code>\n"
            f"📊 <b>تغير الشمعة:</b> {btc_ret * 100:+.2f}%\n"
            f"🛡️ <b>حالة درع الحماية:</b> {status_badge}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔍 <b>حالة السكرينر:</b> يفحص 72 عملة دورياً.\n"
            f"💡 <b>قاعدة النظام:</b> يتم حظر صفقات العملات البديلة فوراً إذا هبط البيتكوين أسفل EMA 50."
        )
        self.send_message(chat_id, radar_msg)
