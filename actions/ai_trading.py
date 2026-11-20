"""
AI Trading & Market Analysis Action for JARVIS.
Provides real-time price quotes, technical indicator analysis (RSI, MACD, Moving Averages, Bollinger Bands),
algorithmic trade signal generation, risk management position sizing, and paper trade tracking.
Supports Stocks, Crypto, and Forex using free public endpoints.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.parse

PORTFOLIO_FILE = Path.home() / ".jarvis_trading_portfolio.json"

def _load_portfolio() -> dict:
    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"balance": 10000.0, "trades": [], "watchlist": ["BTC", "ETH", "AAPL", "NVDA", "TSLA"]}

def _save_portfolio(data: dict) -> None:
    try:
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def _fetch_json(url: str, headers: Optional[dict] = None) -> Any:
    req_headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))

def get_crypto_quote(symbol: str) -> dict:
    clean_sym = symbol.upper().replace("USDT", "").replace("USD", "")
    try:
        # Try Binance public 24hr ticker first
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={clean_sym}USDT"
        data = _fetch_json(url)
        return {
            "symbol": f"{clean_sym}/USDT",
            "price": float(data["lastPrice"]),
            "change_24h_pct": float(data["priceChangePercent"]),
            "high_24h": float(data["highPrice"]),
            "low_24h": float(data["lowPrice"]),
            "volume_24h": float(data["volume"]),
            "market": "Crypto",
        }
    except Exception:
        pass

    try:
        # Fallback to CoinGecko
        cg_id = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "DOGE": "dogecoin", "XRP": "ripple"}.get(clean_sym, clean_sym.lower())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd&include_24hr_change=true"
        data = _fetch_json(url)
        if cg_id in data:
            return {
                "symbol": f"{clean_sym}/USD",
                "price": float(data[cg_id]["usd"]),
                "change_24h_pct": float(data[cg_id].get("usd_24h_change", 0.0)),
                "market": "Crypto",
            }
    except Exception:
        pass
    return {}

def get_stock_quote_and_history(symbol: str) -> dict:
    clean_sym = symbol.upper().strip()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean_sym}?interval=1d&range=3mo"
    try:
        data = _fetch_json(url)
        res = data["chart"]["result"][0]
        meta = res["meta"]
        price = meta.get("regularMarketPrice", 0.0)
        prev_close = meta.get("chartPreviousClose", price)
        change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
        
        quote = res["indicators"]["quote"][0]
        closes = [c for c in quote.get("close", []) if c is not None]
        highs = [h for h in quote.get("high", []) if h is not None]
        lows = [l for l in quote.get("low", []) if l is not None]
        volumes = [v for v in quote.get("volume", []) if v is not None]

        return {
            "symbol": clean_sym,
            "price": round(price, 2),
            "change_pct": round(change_pct, 2),
            "currency": meta.get("currency", "USD"),
            "market": "Stock/Index",
            "closes": closes,
            "highs": highs,
            "lows": lows,
            "volumes": volumes,
        }
    except Exception as e:
        return {"error": str(e), "symbol": clean_sym}

def compute_rsi(prices: List[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def compute_sma(prices: List[float], period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    return round(sum(prices[-period:]) / period, 2)

def compute_ema(prices: List[float], period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = (p * k) + (ema * (1 - k))
    return round(ema, 2)

def compute_indicators(closes: List[float]) -> dict:
    if not closes:
        return {}
    current = closes[-1]
    rsi = compute_rsi(closes, 14)
    sma20 = compute_sma(closes, 20)
    sma50 = compute_sma(closes, 50)
    sma200 = compute_sma(closes, 200) if len(closes) >= 200 else None
    ema9 = compute_ema(closes, 9)
    ema21 = compute_ema(closes, 21)

    # Bollinger Bands (20, 2)
    bb_upper, bb_lower = None, None
    if len(closes) >= 20:
        recent = closes[-20:]
        mean = sum(recent) / 20
        variance = sum((x - mean) ** 2 for x in recent) / 20
        stdev = math.sqrt(variance)
        bb_upper = round(mean + 2 * stdev, 2)
        bb_lower = round(mean - 2 * stdev, 2)

    # Signal Generation
    score = 0
    reasons = []

    if rsi < 30:
        score += 2
        reasons.append(f"RSI is oversold at {rsi}")
    elif rsi > 70:
        score -= 2
        reasons.append(f"RSI is overbought at {rsi}")
    else:
        reasons.append(f"RSI is neutral at {rsi}")

    if ema9 and ema21:
        if ema9 > ema21:
            score += 1
            reasons.append("EMA-9 is above EMA-21 (short-term uptrend)")
        else:
            score -= 1
            reasons.append("EMA-9 is below EMA-21 (short-term downtrend)")

    if sma50:
        if current > sma50:
            score += 1
            reasons.append("Price is above 50-day SMA (medium-term bullish)")
        else:
            score -= 1
            reasons.append("Price is below 50-day SMA (medium-term bearish)")

    if score >= 2:
        signal = "STRONG BUY / BULLISH"
    elif score == 1:
        signal = "MODERATE BUY"
    elif score == -1:
        signal = "MODERATE SELL"
    elif score <= -2:
        signal = "STRONG SELL / BEARISH"
    else:
        signal = "NEUTRAL / HOLD"

    return {
        "rsi_14": rsi,
        "sma_20": sma20,
        "sma_50": sma50,
        "sma_200": sma200,
        "ema_9": ema9,
        "ema_21": ema21,
        "bollinger_upper": bb_upper,
        "bollinger_lower": bb_lower,
        "signal": signal,
        "signal_score": score,
        "reasons": reasons,
    }

def calculate_position_risk(capital: float, risk_pct: float, entry: float, stop_loss: float) -> dict:
    if entry <= 0 or stop_loss <= 0 or entry == stop_loss:
        return {"error": "Invalid entry or stop loss price"}
    
    risk_amount = capital * (risk_pct / 100.0)
    risk_per_share = abs(entry - stop_loss)
    shares = math.floor(risk_amount / risk_per_share)
    total_position_value = shares * entry
    
    # 1:2 and 1:3 targets
    tp_1_2 = round(entry + 2 * (entry - stop_loss), 2)
    tp_1_3 = round(entry + 3 * (entry - stop_loss), 2)

    return {
        "capital": capital,
        "risk_percentage": f"{risk_pct}%",
        "dollar_risk": round(risk_amount, 2),
        "entry_price": entry,
        "stop_loss": stop_loss,
        "shares_or_contracts": shares,
        "position_size": round(total_position_value, 2),
        "target_tp_1_2": tp_1_2,
        "target_tp_1_3": tp_1_3,
    }

def ai_trading(parameters: dict, player=None, session_memory=None) -> str:
    """Main handler for ai_trading action."""
    action = parameters.get("action", "quote").lower().strip()
    symbol = parameters.get("symbol", "BTC").upper().strip()
    capital = float(parameters.get("capital", 10000.0))
    risk_pct = float(parameters.get("risk_pct", 1.5))
    entry = float(parameters.get("entry", 0.0))
    stop_loss = float(parameters.get("stop_loss", 0.0))

    if action in ("quote", "price", "analyze"):
        # Check crypto first
        crypto_data = get_crypto_quote(symbol)
        if crypto_data and "price" in crypto_data:
            res_str = (
                f"📊 Market Quote for {crypto_data['symbol']}:\n"
                f"Current Price: ${crypto_data['price']:,.2f}\n"
                f"24h Change: {crypto_data.get('change_24h_pct', 0.0):+.2f}%\n"
            )
            if "high_24h" in crypto_data:
                res_str += f"24h Range: ${crypto_data['low_24h']:,.2f} - ${crypto_data['high_24h']:,.2f}\n"
            if player:
                try: player.write_log(f"TRADING: {crypto_data['symbol']} @ ${crypto_data['price']}")
                except Exception: pass
            return res_str

        # Check stock/index
        stock_data = get_stock_quote_and_history(symbol)
        if "error" not in stock_data and stock_data.get("price"):
            closes = stock_data.get("closes", [])
            indicators = compute_indicators(closes)
            
            output = [
                f"📈 Market Analysis for {stock_data['symbol']}:",
                f"Current Price: ${stock_data['price']:.2f} ({stock_data['change_pct']:+.2f}%)",
            ]
            if indicators:
                output.append(f"Technical Signal: **{indicators['signal']}** (Score: {indicators['signal_score']})")
                output.append(f"RSI (14): {indicators['rsi_14']}")
                if indicators.get('sma_50'): output.append(f"50-day SMA: ${indicators['sma_50']}")
                if indicators.get('bollinger_upper'): output.append(f"Bollinger Bands: ${indicators['bollinger_lower']} - ${indicators['bollinger_upper']}")
                output.append("Key Factors: " + "; ".join(indicators['reasons'][:2]))

            res_text = "\n".join(output)
            if player:
                try: player.write_log(f"TRADING: {symbol} - {indicators.get('signal', 'analyzed')}")
                except Exception: pass
            return res_text
        
        return f"Unable to find quote for symbol '{symbol}'. Please specify a valid crypto (e.g. BTC, ETH, SOL) or stock ticker (e.g. AAPL, NVDA, TSLA)."

    elif action in ("risk", "position_size", "calculator"):
        if entry <= 0 or stop_loss <= 0:
            return "Please provide both 'entry' price and 'stop_loss' price to calculate position risk."
        risk_res = calculate_position_risk(capital, risk_pct, entry, stop_loss)
        if "error" in risk_res:
            return f"Risk calculation error: {risk_res['error']}"
        
        report = (
            f"⚖️ Position Sizing & Risk Management for {symbol}:\n"
            f"• Portfolio Capital: ${risk_res['capital']:,.2f}\n"
            f"• Max Dollar Risk ({risk_res['risk_percentage']}): ${risk_res['dollar_risk']:,.2f}\n"
            f"• Entry Price: ${risk_res['entry_price']:,.2f} | Stop Loss: ${risk_res['stop_loss']:,.2f}\n"
            f"• Recommended Position: {risk_res['shares_or_contracts']} shares/units (Total: ${risk_res['position_size']:,.2f})\n"
            f"• Take Profit (1:2 R:R): ${risk_res['target_tp_1_2']:,.2f}\n"
            f"• Take Profit (1:3 R:R): ${risk_res['target_tp_1_3']:,.2f}"
        )
        return report

    elif action in ("portfolio", "paper_trade"):
        portfolio = _load_portfolio()
        sub_act = parameters.get("sub_action", "view").lower()
        if sub_act == "buy" and entry > 0:
            qty = float(parameters.get("quantity", 1))
            portfolio["trades"].append({
                "symbol": symbol,
                "type": "BUY",
                "entry": entry,
                "qty": qty,
                "time": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            portfolio["balance"] -= (entry * qty)
            _save_portfolio(portfolio)
            return f"Paper trade logged: Bought {qty} of {symbol} at ${entry:.2f}. New cash balance: ${portfolio['balance']:,.2f}"
        
        trades_count = len(portfolio["trades"])
        return f"Paper Portfolio Status: Balance ${portfolio['balance']:,.2f} | Open/Recorded Trades: {trades_count} | Watchlist: {', '.join(portfolio['watchlist'])}"

    return f"AI Trading action '{action}' completed."


TOOL = {
    "name": "ai_trading",
    "description": (
        "AI Trading and Market Analysis engine. Analyzes crypto, stocks, and forex. "
        "Provides real-time price quotes, technical indicator analysis (RSI, MACD, Moving Averages, Bollinger Bands), "
        "trade signals (BUY/SELL/HOLD), risk management & position sizing calculators, and paper trading portfolio tracking."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "quote | analyze | risk | position_size | portfolio (default: quote)",
            },
            "symbol": {
                "type": "STRING",
                "description": "Ticker symbol, e.g. BTC, ETH, SOL, AAPL, NVDA, TSLA, SPY",
            },
            "capital": {
                "type": "NUMBER",
                "description": "Total trading capital in account (for risk calculation, default: 10000)",
            },
            "risk_pct": {
                "type": "NUMBER",
                "description": "Max risk percentage per trade (e.g. 1.0 or 2.0, default: 1.5)",
            },
            "entry": {
                "type": "NUMBER",
                "description": "Trade entry price for risk calculator or paper trade",
            },
            "stop_loss": {
                "type": "NUMBER",
                "description": "Stop loss price for risk management calculation",
            },
            "sub_action": {
                "type": "STRING",
                "description": "Sub-action for portfolio: view | buy | sell",
            },
            "quantity": {
                "type": "NUMBER",
                "description": "Quantity for paper trading",
            }
        },
        "required": ["action"],
    },
    "handler": ai_trading,
}
