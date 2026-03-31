"""
Получение live-данных EUR/USD H1.
Использует Yahoo Finance API напрямую через HTTP (без yfinance).
"""

import time
import json
from datetime import datetime, timezone, timedelta

import pandas as pd
import numpy as np
import requests

from config import SYMBOL, EMA_PERIOD, RSI_PERIOD
from indicators import calc_ema, calc_rsi


# Yahoo Finance chart API endpoint
YF_BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"

# User-Agent чтобы Yahoo не блокировал
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}


def _fetch_yahoo_chart(symbol: str = "EURUSD=X", days_back: int = 30,
                       interval: str = "1h") -> pd.DataFrame:
    """
    Загружает свечи через Yahoo Finance Chart API.
    """
    period1 = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp())
    period2 = int(datetime.now(timezone.utc).timestamp())

    params = {
        "symbol": symbol,
        "period1": period1,
        "period2": period2,
        "interval": interval,
        "includePrePost": "false",
    }

    resp = requests.get(
        f"{YF_BASE_URL}/{symbol}",
        params=params,
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    result = data.get("chart", {}).get("result", [])
    if not result:
        raise RuntimeError(f"Нет данных от Yahoo Finance для {symbol}")

    chart = result[0]
    timestamps = chart["timestamp"]
    quotes = chart["indicators"]["quote"][0]

    df = pd.DataFrame({
        "datetime": pd.to_datetime(timestamps, unit="s", utc=True),
        "open": quotes["open"],
        "high": quotes["high"],
        "low": quotes["low"],
        "close": quotes["close"],
        "volume": quotes.get("volume", [0] * len(timestamps)),
    })

    # Убираем строки с NaN
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    return df


def fetch_h1_candles(days_back: int = 30) -> pd.DataFrame:
    """
    Загружает последние H1-свечи EUR/USD с индикаторами.
    """
    data = _fetch_yahoo_chart("EURUSD=X", days_back=days_back, interval="1h")

    if data.empty:
        raise RuntimeError("Получен пустой набор данных")

    data["date"] = data["datetime"].dt.date
    data["hour"] = data["datetime"].dt.hour
    data["weekday"] = data["datetime"].dt.weekday

    # Индикаторы
    data["ema21"] = calc_ema(data["close"], EMA_PERIOD)
    data["rsi"] = calc_rsi(data["close"], RSI_PERIOD)
    data["body"] = abs(data["close"] - data["open"])
    data["is_bullish"] = data["close"] > data["open"]

    # Заполняем volume нулями если нет
    data["volume"] = data["volume"].fillna(0)

    data = data[["datetime", "date", "hour", "weekday",
                  "open", "high", "low", "close", "volume",
                  "ema21", "rsi", "body", "is_bullish"]].copy()

    return data.sort_values("datetime").reset_index(drop=True)


def get_current_price() -> float:
    """Получает текущую цену EUR/USD через Yahoo Finance."""
    try:
        resp = requests.get(
            f"{YF_BASE_URL}/EURUSD=X",
            params={"interval": "1m", "range": "1d"},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if result:
            meta = result[0].get("meta", {})
            price = meta.get("regularMarketPrice", 0)
            if price > 0:
                return price
    except Exception:
        pass

    # Фоллбэк: последняя цена из chart
    try:
        resp = requests.get(
            f"{YF_BASE_URL}/EURUSD=X",
            params={"interval": "1h", "range": "1d"},
            headers=HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("chart", {}).get("result", [])
        if result:
            closes = result[0]["indicators"]["quote"][0]["close"]
            # Последнее не-None значение
            for c in reversed(closes):
                if c is not None:
                    return c
    except Exception:
        pass

    return 0.0
