"""
Получение live-данных EUR/USD H1.
Использует Yahoo Finance API напрямую через HTTP (без yfinance).
Включает retry-логику и несколько fallback endpoints.
"""

import time
from datetime import datetime, timezone, timedelta

import pandas as pd
import requests

from config import EMA_PERIOD, RSI_PERIOD
from indicators import calc_ema, calc_rsi


# Несколько серверов Yahoo Finance (если один лимитирует — пробуем другой)
YF_HOSTS = [
    "https://query1.finance.yahoo.com",
    "https://query2.finance.yahoo.com",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# Сессия с keep-alive для переиспользования соединения
_session = requests.Session()
_session.headers.update(HEADERS)


def _request_with_retry(path: str, params: dict,
                        max_retries: int = 3, base_delay: float = 5.0) -> dict:
    """
    HTTP GET с retry и exponential backoff по нескольким хостам Yahoo Finance.
    """
    last_error = None

    for attempt in range(max_retries):
        host = YF_HOSTS[attempt % len(YF_HOSTS)]
        url = f"{host}{path}"

        try:
            resp = _session.get(url, params=params, timeout=15)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 429:
                # Rate limited — ждём дольше
                delay = base_delay * (2 ** attempt)
                print(f"  ⏳ Rate limit (429), жду {delay:.0f}с...")
                time.sleep(delay)
                last_error = f"429 Too Many Requests (попытка {attempt + 1})"
                continue

            resp.raise_for_status()

        except requests.exceptions.ConnectionError as e:
            delay = base_delay * (2 ** attempt)
            print(f"  ⏳ Ошибка соединения, жду {delay:.0f}с...")
            time.sleep(delay)
            last_error = str(e)
        except requests.exceptions.Timeout:
            delay = base_delay * (2 ** attempt)
            print(f"  ⏳ Таймаут, жду {delay:.0f}с...")
            time.sleep(delay)
            last_error = "Timeout"
        except Exception as e:
            last_error = str(e)
            break

    raise RuntimeError(f"Не удалось получить данные после {max_retries} попыток: {last_error}")


def _fetch_yahoo_chart(symbol: str = "EURUSD=X", days_back: int = 30,
                       interval: str = "1h") -> pd.DataFrame:
    """
    Загружает свечи через Yahoo Finance Chart API.
    """
    period1 = int((datetime.now(timezone.utc) - timedelta(days=days_back)).timestamp())
    period2 = int(datetime.now(timezone.utc).timestamp())

    params = {
        "period1": period1,
        "period2": period2,
        "interval": interval,
        "includePrePost": "false",
    }

    data = _request_with_retry(f"/v8/finance/chart/{symbol}", params)

    result = data.get("chart", {}).get("result", [])
    if not result:
        raise RuntimeError(f"Нет данных от Yahoo Finance для {symbol}")

    chart = result[0]
    timestamps = chart.get("timestamp", [])
    if not timestamps:
        raise RuntimeError("Пустой список timestamp в ответе Yahoo")

    quotes = chart["indicators"]["quote"][0]

    df = pd.DataFrame({
        "datetime": pd.to_datetime(timestamps, unit="s", utc=True),
        "open": quotes["open"],
        "high": quotes["high"],
        "low": quotes["low"],
        "close": quotes["close"],
        "volume": quotes.get("volume", [0] * len(timestamps)),
    })

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

    data["ema21"] = calc_ema(data["close"], EMA_PERIOD)
    data["rsi"] = calc_rsi(data["close"], RSI_PERIOD)
    data["body"] = abs(data["close"] - data["open"])
    data["is_bullish"] = data["close"] > data["open"]
    data["volume"] = data["volume"].fillna(0)

    data = data[["datetime", "date", "hour", "weekday",
                  "open", "high", "low", "close", "volume",
                  "ema21", "rsi", "body", "is_bullish"]].copy()

    return data.sort_values("datetime").reset_index(drop=True)


def get_current_price() -> float:
    """Получает текущую цену EUR/USD."""
    try:
        data = _request_with_retry(
            "/v8/finance/chart/EURUSD=X",
            params={"interval": "1m", "range": "1d"},
            max_retries=2,
            base_delay=3.0,
        )
        result = data.get("chart", {}).get("result", [])
        if result:
            meta = result[0].get("meta", {})
            price = meta.get("regularMarketPrice", 0)
            if price > 0:
                return price
            # Fallback: последний close
            closes = result[0]["indicators"]["quote"][0].get("close", [])
            for c in reversed(closes):
                if c is not None:
                    return c
    except Exception:
        pass

    return 0.0
