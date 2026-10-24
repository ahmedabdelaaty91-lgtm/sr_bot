import requests
import numpy as np
import pandas as pd
from config import WATCHLIST_PAIRS

def fetch_klines(symbol, interval, limit=120):
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        r = requests.get(url, params=params, timeout=7)
        data = r.json()
        if not data or not isinstance(data, list):
            return pd.DataFrame()
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        return df[["open_time", "open", "high", "low", "close", "volume"]]
    except Exception:
        return pd.DataFrame()

def check_btc_shield():
    df = fetch_klines("BTCUSDT", "4h", limit=80)
    if df.empty or len(df) < 50:
        return True, 0, 0, 0
    close = df["close"]
    ema50 = close.ewm(span=50, adjust=False).mean()
    last_close = close.iloc[-1]
    last_ema = ema50.iloc[-1]
    last_ret = (last_close - close.iloc[-2]) / close.iloc[-2]
    
    is_safe = (last_close >= last_ema) and (last_ret >= -0.018)
    return is_safe, last_close, last_ema, last_ret

def find_recent_supports(df, left=10, right=5):
    n = len(df)
    lows = df["low"].values
    supports = []
    # Only confirmed pivots before the current active candle
    for p in range(left, n - right - 1):
        window = lows[p - left : p + right + 1]
        if lows[p] == np.min(window):
            supports.append(lows[p])
    return supports[-8:] # return last 8 confirmed supports

def check_symbol_setup(symbol):
    df = fetch_klines(symbol, "1h", limit=120)
    if df.empty or len(df) < 35:
        return None
        
    close = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    volumes = df["volume"].values
    
    i = len(df) - 1 # latest completed/forming candle
    
    # 1. Calculate RSI(14)
    delta = pd.Series(close).diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-9)
    rsi14 = (100 - (100 / (1 + rs))).values
    if np.isnan(rsi14[i]) or rsi14[i] > 48.0:
        return None
        
    # 2. Support Level Check
    supports = find_recent_supports(df, left=10, right=5)
    if not supports:
        return None
        
    curr_c = close[i]
    valid_supports = [s for s in supports if s <= curr_c * 1.025]
    if not valid_supports:
        return None
    support_level = max(valid_supports)
    
    # 3. Candlestick Pattern Detection
    o, c, h, l = opens[i], close[i], highs[i], lows[i]
    body = abs(c - o)
    lower_shadow = min(o, c) - l
    
    vol_ma20 = np.mean(volumes[max(0, i-20):i])
    has_vol = volumes[i] >= 1.05 * vol_ma20
    
    pattern = None
    pattern_low = l
    
    # SFP Liquidity Sweep
    if l < support_level and c >= support_level * 0.998:
        if lower_shadow >= 1.4 * body:
            pattern = "Liquidity Sweep (SFP)"
            pattern_low = l

    # Bullish Engulfing
    if not pattern and c > o and close[i-1] < opens[i-1]:
        if c >= opens[i-1] and o <= close[i-1]:
            if has_vol:
                pattern = "Bullish Engulfing"
                pattern_low = min(l, lows[i-1])

    # Morning Star
    if not pattern and i >= 2:
        if close[i-2] < opens[i-2] and c > o:
            mid_body = abs(close[i-1] - opens[i-1])
            first_body = opens[i-2] - close[i-2]
            if mid_body <= 0.45 * first_body and c > (opens[i-2] + close[i-2]) / 2.0:
                pattern = "Morning Star"
                pattern_low = min(l, lows[i-1], lows[i-2])
                
    if not pattern:
        return None
        
    # ATR(14)
    hl = pd.Series(highs) - pd.Series(lows)
    hc = (pd.Series(highs) - pd.Series(close).shift()).abs()
    lc = (pd.Series(lows) - pd.Series(close).shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean().values[-1]
    
    atr_buf = 0.5 * atr14 if not np.isnan(atr14) else (c * 0.01)
    entry = c
    sl = min(pattern_low, support_level) - atr_buf
    risk = entry - sl
    
    risk_pct = risk / entry
    if risk_pct < 0.005 or risk_pct > 0.08:
        return None
        
    tp1 = entry + 1.5 * risk
    tp2 = entry + 2.5 * risk
    
    return {
        "symbol": symbol,
        "pattern": pattern,
        "entry": entry,
        "sl": sl,
        "risk": risk,
        "risk_pct": round(risk_pct * 100, 2),
        "tp1": tp1,
        "tp2": tp2,
        "support": support_level,
        "rsi": round(rsi14[i], 1)
    }
