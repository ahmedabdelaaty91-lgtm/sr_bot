import time
import math
import hmac
import hashlib
import requests
import json
from config import BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_BASE_URL

class BinanceClient:
    def __init__(self):
        self.api_key = BINANCE_API_KEY
        self.api_secret = BINANCE_API_SECRET
        self.base_url = BINANCE_BASE_URL
        self.headers = {"X-MBX-APIKEY": self.api_key}
        self.symbols_info = {}
        self._load_all_symbol_info()

    def _sign(self, params):
        params["timestamp"] = int(time.time() * 1000)
        query = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        sig = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return f"{query}&signature={sig}"

    def _load_all_symbol_info(self):
        try:
            r = requests.get(f"{self.base_url}/api/v3/exchangeInfo", timeout=10).json()
            for s in r.get("symbols", []):
                sym = s["symbol"]
                lot = next((f for f in s["filters"] if f["filterType"] == "LOT_SIZE"), None)
                price_f = next((f for f in s["filters"] if f["filterType"] == "PRICE_FILTER"), None)
                min_not = next((f for f in s["filters"] if f["filterType"] in ("MIN_NOTIONAL", "NOTIONAL")), None)
                
                step = float(lot["stepSize"]) if lot else 0.001
                min_q = float(lot["minQty"]) if lot else 0.001
                tick = float(price_f["tickSize"]) if price_f else 0.01
                notional = float(min_not.get("minNotional", min_not.get("notional", 5.0))) if min_not else 5.0
                
                # compute decimal precision from stepSize
                precision = 0
                if step < 1.0 and step > 0:
                    try:
                        precision = max(0, int(round(-math.log10(step))))
                    except Exception:
                        precision = 4
                    
                self.symbols_info[sym] = {
                    "stepSize": step,
                    "minQty": min_q,
                    "tickSize": tick,
                    "minNotional": notional,
                    "precision": precision
                }
        except Exception as e:
            print(f"Error loading exchangeInfo: {e}")

    def get_usdt_balance(self):
        try:
            params = {}
            signed_query = self._sign(params)
            r = requests.get(f"{self.base_url}/api/v3/account?{signed_query}", headers=self.headers, timeout=5)
            data = r.json()
            for b in data.get("balances", []):
                if b["asset"] == "USDT":
                    return float(b["free"])
            return 0.0
        except Exception as e:
            print(f"Error getting USDT balance: {e}")
            return 0.0

    def get_ticker_price(self, symbol):
        # We can check Testnet, or public Binance live for accurate market pricing
        try:
            r = requests.get(f"https://api.binance.com/api/v3/ticker/price", params={"symbol": symbol}, timeout=5).json()
            if "price" in r:
                return float(r["price"])
        except Exception:
            pass
        # Fallback to testnet
        try:
            r = requests.get(f"{self.base_url}/api/v3/ticker/price", params={"symbol": symbol}, timeout=5).json()
            if "price" in r:
                return float(r["price"])
        except Exception as e:
            print(f"Error getting price for {symbol}: {e}")
        return 0.0

    def round_qty(self, symbol, qty):
        info = self.symbols_info.get(symbol)
        if not info:
            return round(qty, 4)
        precision = info["precision"]
        step = info["stepSize"]
        # Floor to avoid insufficient funds
        rounded = math.floor(qty / step) * step
        return round(rounded, precision)

    def market_buy(self, symbol, usdt_amount):
        price = self.get_ticker_price(symbol)
        if price <= 0:
            return None, "Invalid price"
            
        raw_qty = usdt_amount / price
        qty = self.round_qty(symbol, raw_qty)
        
        info = self.symbols_info.get(symbol, {})
        min_qty = info.get("minQty", 0.0001)
        if qty < min_qty:
            return None, f"Quantity {qty} below minQty {min_qty}"

        params = {
            "symbol": symbol,
            "side": "BUY",
            "type": "MARKET",
            "quantity": qty
        }
        try:
            signed_query = self._sign(params)
            r = requests.post(f"{self.base_url}/api/v3/order?{signed_query}", headers=self.headers, timeout=7)
            res = r.json()
            if "orderId" in res:
                # Calculate executed avg price
                exec_price = price
                fills = res.get("fills", [])
                if fills:
                    total_spent = sum(float(f["price"]) * float(f["qty"]) for f in fills)
                    total_qty = sum(float(f["qty"]) for f in fills)
                    if total_qty > 0:
                        exec_price = total_spent / total_qty
                return {
                    "orderId": res["orderId"],
                    "symbol": symbol,
                    "qty": qty,
                    "price": exec_price,
                    "cost": qty * exec_price
                }, None
            else:
                return None, res.get("msg", str(res))
        except Exception as e:
            return None, str(e)

    def market_sell(self, symbol, qty):
        qty = self.round_qty(symbol, qty)
        info = self.symbols_info.get(symbol, {})
        min_qty = info.get("minQty", 0.0001)
        if qty < min_qty:
            return None, f"Quantity {qty} below minQty {min_qty}"

        params = {
            "symbol": symbol,
            "side": "SELL",
            "type": "MARKET",
            "quantity": qty
        }
        try:
            signed_query = self._sign(params)
            r = requests.post(f"{self.base_url}/api/v3/order?{signed_query}", headers=self.headers, timeout=7)
            res = r.json()
            if "orderId" in res:
                price = self.get_ticker_price(symbol)
                fills = res.get("fills", [])
                if fills:
                    total_spent = sum(float(f["price"]) * float(f["qty"]) for f in fills)
                    total_qty = sum(float(f["qty"]) for f in fills)
                    if total_qty > 0:
                        price = total_spent / total_qty
                return {
                    "orderId": res["orderId"],
                    "symbol": symbol,
                    "qty": qty,
                    "price": price
                }, None
            else:
                return None, res.get("msg", str(res))
        except Exception as e:
            return None, str(e)
