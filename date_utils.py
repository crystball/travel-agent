from __future__ import annotations

import os
import re
from datetime import date, timedelta

from state import RoutingInfo, TravelRequirement


CHINESE_NUMERALS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def parse_days(text: str) -> int | None:
    digit_match = re.search(r"(\d+)\s*天", text)
    if digit_match:
        return int(digit_match.group(1))

    chinese_match = re.search(r"([一二两三四五六七八九十]+)\s*天", text)
    if not chinese_match:
        return None

    token = chinese_match.group(1)
    if token == "十":
        return 10
    if token.startswith("十"):
        return 10 + CHINESE_NUMERALS.get(token[1:], 0)
    if token.endswith("十"):
        return CHINESE_NUMERALS.get(token[0], 0) * 10
    if "十" in token:
        left, right = token.split("十", maxsplit=1)
        return CHINESE_NUMERALS.get(left, 0) * 10 + CHINESE_NUMERALS.get(right, 0)
    return CHINESE_NUMERALS.get(token)


def parse_first_date(text: str, today: date | None = None) -> date | None:
    today = today or date.today()

    full_date_match = re.search(
        r"(20\d{2})[年\-/](\d{1,2})[月\-/](\d{1,2})日?", text
    )
    if full_date_match:
        year, month, day = map(int, full_date_match.groups())
        return date(year, month, day)

    short_date_match = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if not short_date_match:
        return None

    month, day = map(int, short_date_match.groups())
    candidate = date(today.year, month, day)
    if candidate < today:
        candidate = date(today.year + 1, month, day)
    return candidate


def parse_date_range(text: str, today: date | None = None) -> tuple[date | None, date | None]:
    today = today or date.today()
    full_dates = [
        date(*map(int, groups))
        for groups in re.findall(
            r"(20\d{2})[年\-/](\d{1,2})[月\-/](\d{1,2})日?",
            text,
        )
    ]
    if len(full_dates) >= 2:
        return full_dates[0], full_dates[1]

    first = parse_first_date(text, today=today)
    if first is None:
        return None, None

    month_day_matches = re.findall(r"(\d{1,2})月(\d{1,2})日", text)
    if len(month_day_matches) >= 2:
        month, day = map(int, month_day_matches[1])
        end = date(first.year, month, day)
        if end < first:
            end = date(first.year + 1, month, day)
        return first, end

    trailing_day_match = re.search(r"(?:到|至|~|～|-|—)\s*(\d{1,2})日", text)
    if trailing_day_match:
        end = date(first.year, first.month, int(trailing_day_match.group(1)))
        if end < first:
            end = date(first.year + 1, first.month, end.day)
        return first, end

    return first, None


def infer_days(start_date: date | None, end_date: date | None) -> int | None:
    if not start_date or not end_date:
        return None
    days = (end_date - start_date).days + 1
    return days if days > 0 else None


def remove_date_expressions(text: str) -> str:
    cleaned = re.sub(
        r"20\d{2}[年\-/]\d{1,2}[月\-/]\d{1,2}日?\s*(?:到|至|~|～|-|—)\s*20\d{2}[年\-/]\d{1,2}[月\-/]\d{1,2}日?",
        " ",
        text,
    )
    cleaned = re.sub(
        r"\d{1,2}月\d{1,2}日\s*(?:到|至|~|～|-|—)\s*\d{1,2}月\d{1,2}日",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        r"\d{1,2}月\d{1,2}日\s*(?:到|至|~|～|-|—)\s*\d{1,2}日",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"20\d{2}[年\-/]\d{1,2}[月\-/]\d{1,2}日?", " ", cleaned)
    cleaned = re.sub(r"\d{1,2}月\d{1,2}日", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def infer_end_date(start_date: date | None, days: int | None) -> date | None:
    if not start_date or not days:
        return None
    return start_date + timedelta(days=days - 1)


def days_until(target: date | None, today: date | None = None) -> int | None:
    if target is None:
        return None
    today = today or date.today()
    return (target - today).days


def build_routing_info(
    requirement: TravelRequirement, today: date | None = None
) -> RoutingInfo:
    today = today or date.today()
    days_until_departure = days_until(requirement.start_date, today=today)
    weather_window_days = _weather_window_days()

    weather_available = (
        days_until_departure is not None and 0 <= days_until_departure < weather_window_days
    )
    train_query_available = (
        days_until_departure is not None and 0 <= days_until_departure <= 14
    )
    flight_query_available = (
        days_until_departure is not None and 0 <= days_until_departure <= 60
    )
    hotel_query_available = (
        days_until_departure is not None and 0 <= days_until_departure <= 60
    )

    degradation_reasons: list[str] = []
    if not weather_available:
        degradation_reasons.append("超出天气预报有效范围")
    if not train_query_available:
        degradation_reasons.append("超出12306可查询窗口")
    if not flight_query_available:
        degradation_reasons.append("超出机票实时查询窗口")
    if not hotel_query_available:
        degradation_reasons.append("超出酒店实时查询窗口")

    if train_query_available and flight_query_available:
        transport_mode_strategy = "mixed"
    elif train_query_available:
        transport_mode_strategy = "train_first"
    elif flight_query_available:
        transport_mode_strategy = "flight_first"
    else:
        transport_mode_strategy = "reference_only"

    degraded_mode = bool(degradation_reasons)
    data_freshness_note = (
        "部分结果可能为参考信息，请在出行前再次确认。"
        if degraded_mode
        else "当前结果基于可查询的实时数据源。"
    )

    return RoutingInfo(
        days_until_departure=days_until_departure,
        weather_available=weather_available,
        train_query_available=train_query_available,
        flight_query_available=flight_query_available,
        hotel_query_available=hotel_query_available,
        transport_mode_strategy=transport_mode_strategy,
        degraded_mode=degraded_mode,
        degradation_reasons=degradation_reasons,
        data_freshness_note=data_freshness_note,
    )


def _weather_window_days() -> int:
    try:
        return max(1, int(os.getenv("SENIVERSE_MAX_FORECAST_DAYS", "14")))
    except ValueError:
        return 14
