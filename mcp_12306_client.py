from __future__ import annotations

import asyncio
import json
import os
import shlex
from datetime import date, datetime, timedelta
from typing import Any

from state import TransportOption


class MCP12306Client:
    """12306 MCP stdio client wrapper."""

    def __init__(
        self,
        *,
        command: str | None = None,
        args: list[str] | None = None,
    ) -> None:
        self.command = command or os.getenv("MCP_12306_COMMAND") or "npx"
        raw_args = os.getenv("MCP_12306_ARGS")
        self.args = args or (
            shlex.split(raw_args) if raw_args else ["-y", "12306-mcp"]
        )

    def query_tickets(
        self,
        *,
        origin_city: str,
        destination_city: str,
        travel_date: date,
        limit: int = 5,
    ) -> list[TransportOption]:
        try:
            records = asyncio.run(
                self._query_ticket_records(
                    origin_city=origin_city,
                    destination_city=destination_city,
                    travel_date=travel_date,
                    limit=limit,
                )
            )
        except Exception:
            return []

        return [
            option
            for record in records
            if (
                option := _normalize_train_record(
                    record=record,
                    origin_city=origin_city,
                    destination_city=destination_city,
                    travel_date=travel_date,
                )
            )
        ]

    async def _query_ticket_records(
        self,
        *,
        origin_city: str,
        destination_city: str,
        travel_date: date,
        limit: int,
    ) -> list[dict[str, Any]]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=None,
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                from_station, to_station = await _resolve_station_codes(
                    session=session,
                    origin_city=origin_city,
                    destination_city=destination_city,
                )
                result = await session.call_tool(
                    "get-tickets",
                    arguments={
                        "date": travel_date.isoformat(),
                        "fromStation": from_station,
                        "toStation": to_station,
                        "trainFilterFlags": "GD",
                        "sortFlag": "startTime",
                        "sortReverse": False,
                        "limitedNum": limit,
                        "format": "json",
                    },
                )
                text_chunks = [
                    item.text
                    for item in result.content
                    if getattr(item, "type", None) == "text"
                ]
                if not text_chunks:
                    return []
                payload = json.loads("\n".join(text_chunks))
                return _extract_records(payload)


async def _resolve_station_codes(
    *,
    session: Any,
    origin_city: str,
    destination_city: str,
) -> tuple[str, str]:
    result = await session.call_tool(
        "get-station-code-of-citys",
        arguments={"citys": f"{origin_city}|{destination_city}"},
    )
    text_chunks = [
        item.text
        for item in result.content
        if getattr(item, "type", None) == "text"
    ]
    try:
        payload = json.loads("\n".join(text_chunks))
    except (TypeError, json.JSONDecodeError):
        return origin_city, destination_city

    return (
        _extract_station_code(payload, origin_city) or origin_city,
        _extract_station_code(payload, destination_city) or destination_city,
    )


def _extract_station_code(payload: Any, city: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    city_payload = payload.get(city)
    if not isinstance(city_payload, dict):
        return None
    station_code = city_payload.get("station_code")
    return str(station_code) if station_code else None


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("data", "tickets", "result", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_train_record(
    *,
    record: dict[str, Any],
    origin_city: str,
    destination_city: str,
    travel_date: date,
) -> TransportOption | None:
    train_code = _pick_first(
        record,
        "start_train_code",
        "train_code",
        "trainCode",
        "station_train_code",
    )
    departure_time, arrival_time = _build_train_datetimes(record, travel_date)
    duration_minutes = _duration_to_minutes(_pick_first(record, "lishi", "duration"))
    price = _pick_price(record)

    if not train_code and not departure_time and price is None:
        return None

    return TransportOption(
        mode="train",
        provider="12306 MCP",
        departure_city=origin_city,
        arrival_city=destination_city,
        departure_time=departure_time,
        arrival_time=arrival_time,
        duration_minutes=duration_minutes,
        price=price,
        seat_or_class=_pick_seat(record),
        raw_reference=str(train_code) if train_code is not None else None,
    )


def _pick_first(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, ""):
            return record[key]
    return None


def _pick_price(record: dict[str, Any]) -> float | None:
    preferred_price = _pick_price_from_prices(record.get("prices"))
    if preferred_price is not None:
        return preferred_price

    for key in ("second_class_price", "secondClassPrice", "price"):
        parsed = _safe_float(record.get(key))
        if parsed is not None:
            return parsed
    return None


def _pick_seat(record: dict[str, Any]) -> str | None:
    preferred_seat = _pick_seat_from_prices(record.get("prices"))
    if preferred_seat is not None:
        return preferred_seat

    for key in ("seat", "seat_type", "seatType"):
        value = record.get(key)
        if value:
            return str(value)
    return None


def _build_train_datetimes(
    record: dict[str, Any],
    requested_travel_date: date,
) -> tuple[datetime | None, datetime | None]:
    start_time = _pick_first(record, "start_time", "startTime")
    arrive_time = _pick_first(record, "arrive_time", "arriveTime")
    if not start_time:
        return None, None

    departure_time = _parse_train_datetime(
        start_time,
        requested_travel_date.isoformat(),
    )
    if departure_time is None:
        return None, None

    arrival_date = requested_travel_date + timedelta(
        days=_arrival_day_delta(record, start_time, arrive_time)
    )
    arrival_time = _parse_train_datetime(
        arrive_time,
        arrival_date.isoformat(),
    )
    return departure_time, arrival_time


def _arrival_day_delta(record: dict[str, Any], start_time: Any, arrive_time: Any) -> int:
    raw_start_date = record.get("start_date")
    raw_arrive_date = record.get("arrive_date")
    try:
        if raw_start_date and raw_arrive_date:
            start_date_value = date.fromisoformat(str(raw_start_date))
            arrive_date_value = date.fromisoformat(str(raw_arrive_date))
            return max(0, (arrive_date_value - start_date_value).days)
    except ValueError:
        pass

    if start_time and arrive_time and str(arrive_time) < str(start_time):
        return 1
    return 0


def _pick_price_from_prices(prices: Any) -> float | None:
    preferred = _find_preferred_price_item(prices)
    return _safe_float(preferred.get("price")) if preferred else None


def _pick_seat_from_prices(prices: Any) -> str | None:
    preferred = _find_preferred_price_item(prices)
    if not preferred:
        return None
    seat_name = preferred.get("seat_name")
    return str(seat_name) if seat_name else None


def _find_preferred_price_item(prices: Any) -> dict[str, Any] | None:
    if not isinstance(prices, list):
        return None

    valid_items = [item for item in prices if isinstance(item, dict)]
    available_second_class = next(
        (
            item
            for item in valid_items
            if item.get("seat_name") == "二等座" and _seat_is_available(item.get("num"))
        ),
        None,
    )
    if available_second_class is not None:
        return available_second_class

    second_class = next(
        (item for item in valid_items if item.get("seat_name") == "二等座"),
        None,
    )
    if second_class is not None:
        return second_class

    return next(
        (item for item in valid_items if _safe_float(item.get("price")) is not None),
        None,
    )


def _seat_is_available(value: Any) -> bool:
    return value not in (None, "", "无", "0", 0)


def _parse_train_datetime(value: Any, date_value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, str) and "T" in value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    if not date_value:
        return None
    try:
        return datetime.fromisoformat(f"{date_value}T{value}")
    except ValueError:
        return None


def _duration_to_minutes(value: Any) -> int | None:
    if not value:
        return None
    text = str(value)
    if ":" in text:
        hours, minutes = text.split(":", maxsplit=1)
        if hours.isdigit() and minutes.isdigit():
            return int(hours) * 60 + int(minutes)
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).replace("¥", "").replace("元", "").strip()
    try:
        return float(text)
    except ValueError:
        return None
