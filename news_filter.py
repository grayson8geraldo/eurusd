"""
Фильтр экономических новостей.
Определяет, есть ли сегодня важные события (NFP, ECB, Fed, CPI),
при которых нельзя торговать.
"""

import json
import os
from datetime import date, datetime, timezone, timedelta

import requests


# Кэш файл для новостей (чтобы не дёргать API каждый раз)
NEWS_CACHE_FILE = "news_cache.json"
NEWS_CACHE_TTL_HOURS = 12

# Ключевые слова для опасных новостей (high impact для USD и EUR)
HIGH_IMPACT_KEYWORDS = [
    "Non-Farm Payrolls",
    "Nonfarm Payrolls",
    "NFP",
    "ECB Interest Rate",
    "ECB Monetary Policy",
    "ECB Press Conference",
    "Fed Interest Rate",
    "Federal Funds Rate",
    "FOMC Statement",
    "FOMC Press Conference",
    "CPI m/m",
    "CPI y/y",
    "Core CPI",
    "Consumer Price Index",
    "ECB Rate Decision",
    "Fed Rate Decision",
    "Monetary Policy Statement",
]

# Валюты, которые нас интересуют
RELEVANT_CURRENCIES = {"USD", "EUR"}


def _load_cache() -> dict | None:
    """Загружает кэш новостей."""
    if not os.path.exists(NEWS_CACHE_FILE):
        return None
    try:
        with open(NEWS_CACHE_FILE, "r") as f:
            cache = json.load(f)
        cached_time = datetime.fromisoformat(cache["fetched_at"])
        if datetime.now(timezone.utc) - cached_time > timedelta(hours=NEWS_CACHE_TTL_HOURS):
            return None
        return cache
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def _save_cache(data: dict):
    """Сохраняет кэш новостей."""
    data["fetched_at"] = datetime.now(timezone.utc).isoformat()
    with open(NEWS_CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def fetch_news_from_api() -> list[dict]:
    """
    Получает экономический календарь из бесплатного API nager.date + резервный метод.
    Используем несколько источников.
    """
    events = []

    # Метод 1: ForexFactory-стиль через бесплатный API
    try:
        today = date.today()
        url = f"https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            raw_events = resp.json()
            for ev in raw_events:
                events.append({
                    "title": ev.get("title", ""),
                    "country": ev.get("country", ""),
                    "date": ev.get("date", ""),
                    "impact": ev.get("impact", ""),
                })
    except Exception:
        pass

    return events


def is_high_impact_news_today() -> tuple[bool, list[str]]:
    """
    Проверяет, есть ли сегодня важные новости для EUR или USD.

    Возвращает:
        (True/False, список названий событий)
    """
    # Проверяем кэш
    cache = _load_cache()
    if cache and "events" in cache:
        events = cache["events"]
    else:
        events = fetch_news_from_api()
        _save_cache({"events": events})

    today_str = date.today().isoformat()
    dangerous = []

    for ev in events:
        ev_date = ev.get("date", "")
        # Форматы дат из API могут быть разные
        if today_str not in ev_date:
            continue

        country = ev.get("country", "").upper()
        impact = ev.get("impact", "").lower()
        title = ev.get("title", "")

        # Только high impact для USD/EUR
        if impact not in ("high",):
            continue
        if country not in RELEVANT_CURRENCIES:
            continue

        # Проверяем по ключевым словам
        for kw in HIGH_IMPACT_KEYWORDS:
            if kw.lower() in title.lower():
                dangerous.append(f"[{country}] {title}")
                break

    return len(dangerous) > 0, dangerous


def should_skip_trading() -> tuple[bool, str]:
    """
    Комплексная проверка: стоит ли пропустить торговлю сегодня.

    Возвращает:
        (True/False, причина)
    """
    now = datetime.now(timezone.utc)

    # Суббота/воскресенье
    if now.weekday() >= 5:
        return True, "Выходной день"

    # Пятница после 15:00 UTC
    if now.weekday() == 4 and now.hour >= 15:
        return True, "Пятница после 15:00 UTC"

    # Проверка новостей
    try:
        has_news, news_list = is_high_impact_news_today()
        if has_news:
            return True, f"Важные новости: {', '.join(news_list)}"
    except Exception as e:
        # Если API недоступен — не блокируем торговлю, но предупреждаем
        print(f"  ⚠ Не удалось проверить новости: {e}")

    return False, ""
