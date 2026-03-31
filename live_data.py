"""
Получение live-данных EUR/USD H1.
Использует Twelve Data API (бесплатно, 800 запросов/день).
Регистрация: https://twelvedata.com/register
"""

import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests

from config import TWELVEDATA_API_KEY, SYMBOL, EMA_PERIOD, RSI_PERIOD
from indicators import calc_ema, calc_rsi


TD_BASE = "https://api.twelvedata.com"

_session = requests.Session()


def _get_api_key() -> str:
    """Получает API ключ из config или переменной окружения."""
    key = TWELVEDATA_API_KEY or os.environ.get("TWELVEDATA_API_KEY", "")
    if not key:
        raise RuntimeError(
            "\n╔══════════════════════════════════════════════════════════╗\n"
            "║  API ключ не найден!                                    ║\n"
            "║                                                         ║\n"
            "║  1. Зайдите на https://twelvedata.com/register          ║\n"
            "║  2. Скопируйте API ключ из Dashboard                    ║\n"
            "║  3. Вставьте в config.py → TWELVEDATA_API_KEY           ║\n"
            "║     или задайте переменную окружения:                    ║\n"
            "║     export TWELVEDATA_API_KEY=ваш_ключ                  ║\n"
            "╚══════════════════════════════════════════════════════════╝"
        )
    return key


def _td_request(endpoint: str, params: dict, max_retries: int = 3) -> dict:
    """HTTP GET к Twelve Data API с retry."""
    params["apikey"] = _get_api_key()
    last_error = None

    for attempt in range(max_retries):
        try:
            resp = _session.get(f"{TD_BASE}/{endpoint}", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            # Twelve Data возвращает ошибки в JSON
            if data.get("status") == "error":
                msg = data.get("message", "Unknown error")
                if "API key" in msg:
                    raise RuntimeError(f"Неверный API ключ: {msg}")
                if "limit" in msg.lower():
                    delay = 10 * (2 ** attempt)
                    print(f"  ⏳ API лимит, жду {delay}с...")
                    time.sleep(delay)
                    last_error = msg
                    continue
                raise RuntimeError(f"Twelve Data API: {msg}")

            return data

        except requests.exceptions.RequestException as e:
            delay = 5 * (2 ** attempt)
            print(f"  ⏳ Ошибка сети, жду {delay}с...")
            time.sleep(delay)
            last_error = str(e)

    raise RuntimeError(f"Не удалось получить данные после {max_retries} попыток: {last_error}")


def fetch_h1_candles(days_back: int = 30) -> pd.DataFrame:
    """
    Загружает последние H1-свечи EUR/USD с индикаторами.
    Twelve Data бесплатно даёт до 5000 строк.
    """
    output_size = min(days_back * 24, 5000)

    data = _td_request("time_series", {
        "symbol": SYMBOL,
        "interval": "1h",
        "outputsize": output_size,
        "timezone": "UTC",
        "format": "JSON",
    })

    values = data.get("values", [])
    if not values:
        raise RuntimeError("Нет данных от Twelve Data API")

    df = pd.DataFrame(values)
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)

    # Volume может отсутствовать для forex
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    else:
        df["volume"] = 0.0

    df = df.sort_values("datetime").reset_index(drop=True)

    df["date"] = df["datetime"].dt.date
    df["hour"] = df["datetime"].dt.hour
    df["weekday"] = df["datetime"].dt.weekday

    df["ema21"] = calc_ema(df["close"], EMA_PERIOD)
    df["rsi"] = calc_rsi(df["close"], RSI_PERIOD)
    df["body"] = abs(df["close"] - df["open"])
    df["is_bullish"] = df["close"] > df["open"]

    df = df[["datetime", "date", "hour", "weekday",
              "open", "high", "low", "close", "volume",
              "ema21", "rsi", "body", "is_bullish"]].copy()

    return df


def get_current_price() -> float:
    """Получает текущую цену EUR/USD."""
    try:
        data = _td_request("price", {
            "symbol": SYMBOL,
        }, max_retries=2)
        price = float(data.get("price", 0))
        if price > 0:
            return price
    except Exception:
        pass

    # Фоллбэк: последняя свеча
    try:
        data = _td_request("time_series", {
            "symbol": SYMBOL,
            "interval": "1min",
            "outputsize": 1,
            "timezone": "UTC",
        }, max_retries=2)
        values = data.get("values", [])
        if values:
            return float(values[0]["close"])
    except Exception:
        pass

    return 0.0
