from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import date, datetime
from typing import Any

from dotenv import load_dotenv

from llm_client import DeepSeekClient
from state import Attraction, Hotel, Location, Restaurant, TransportOption


load_dotenv()


MAX_FLIGHT_TRANSFER_DURATION_MINUTES = 120


class FlyAIClient:
    """FlyAI CLI adapter.

    Public FlyAI docs currently describe a CLI workflow. This adapter keeps that
    detail out of the agents and normalizes raw CLI text into project models.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        command: str | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.api_key = api_key or os.getenv("FLYAI_API_KEY")
        self.command = command or os.getenv("FLYAI_COMMAND") or "flyai"
        self.timeout = timeout
        self.last_command: list[str] | None = None
        self.last_stdout: str | None = None
        self.last_stderr: str | None = None
        self.last_payload: dict[str, Any] | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key) and self._command_exists()

    def search_flights(
        self, origin_city: str, destination_city: str, travel_date: date
    ) -> list[TransportOption]:
        if not self.configured:
            return []
        payload = self._run_json_command(
            [
                "search-flight",
                "--origin",
                origin_city,
                "--destination",
                destination_city,
                "--dep-date",
                travel_date.isoformat(),
                "--sort-type",
                "3",
            ]
        )
        return self._parse_flights(
            payload=payload,
            origin_city=origin_city,
            destination_city=destination_city,
        )

    def search_hotels(
        self,
        destination_city: str,
        check_in: date,
        check_out: date,
        hotel_preference: str | None = None,
        poi_name: str | None = None,
    ) -> list[Hotel]:
        if not self.configured:
            return []
        command = [
            "search-hotel",
            "--dest-name",
            destination_city,
            "--check-in-date",
            check_in.isoformat(),
            "--check-out-date",
            check_out.isoformat(),
            "--sort",
            "rate_desc",
        ]
        if poi_name:
            command.extend(["--poi-name", poi_name])
        if hotel_preference:
            command.extend(["--key-words", hotel_preference])
        payload = self._run_json_command(command)
        return self._parse_hotels(payload)

    def search_attractions(
        self, destination_city: str, preferences: list[str] | None = None
    ) -> list[Attraction]:
        if not self.configured:
            return []
        command = ["search-poi", "--city-name", destination_city]
        keyword = _pick_attraction_keyword(preferences or [])
        if keyword:
            command.extend(["--keyword", keyword])
        payload = self._run_json_command(command)
        return self._parse_attractions(payload)

    def search_restaurants(
        self, destination_city: str, preferences: list[str] | None = None
    ) -> list[Restaurant]:
        if not self.configured:
            return []
        preference_text = "、".join(preferences or []) or "当地特色"
        payload = self._run_json_command(
            [
                "keyword-search",
                "--query",
                f"{destination_city} {preference_text} 美食 餐厅",
            ]
        )
        return self._parse_restaurants(payload)

    def _run_json_command(self, args: list[str]) -> dict[str, Any]:
        env = os.environ.copy()
        env["FLYAI_API_KEY"] = self.api_key or ""
        self.last_command = self._build_subprocess_command(args)
        with tempfile.NamedTemporaryFile(delete=False) as stdout_file, tempfile.NamedTemporaryFile(
            delete=False
        ) as stderr_file:
            stdout_path = stdout_file.name
            stderr_path = stderr_file.name

        try:
            with open(stdout_path, "wb") as stdout_handle, open(
                stderr_path, "wb"
            ) as stderr_handle:
                completed = subprocess.run(
                    self.last_command,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    timeout=self.timeout,
                    check=False,
                    env=env,
                )
            self.last_stdout = _read_text_file(stdout_path)
            self.last_stderr = _read_text_file(stderr_path)
        finally:
            for path in (stdout_path, stderr_path):
                try:
                    os.remove(path)
                except OSError:
                    pass

        stdout = (self.last_stdout or "").strip()
        payload = _try_parse_json(stdout)
        self.last_payload = payload

        # On Windows, the FlyAI CLI can emit a complete success payload and then
        # still exit abnormally during process shutdown. Prefer a valid service
        # response over the wrapper process return code so callers can use the
        # data that was already produced.
        if payload is not None and payload.get("status") == 0:
            return payload

        if completed.returncode != 0:
            raise RuntimeError((self.last_stderr or "").strip() or "FlyAI command failed.")

        if payload is not None:
            return payload

        if not stdout:
            return {}

        raise RuntimeError("FlyAI returned non-JSON output.")

    def _command_exists(self) -> bool:
        if os.path.isabs(self.command):
            return os.path.exists(self.command)
        return shutil.which(self.command) is not None

    def _build_subprocess_command(self, args: list[str]) -> list[str]:
        if os.name == "nt":
            return ["cmd.exe", "/c", self.command, *args]
        return [self.command, *args]

    def _parse_flights(
        self, *, payload: dict[str, Any], origin_city: str, destination_city: str
    ) -> list[TransportOption]:
        options = []
        for item in ((payload.get("data") or {}).get("itemList") or []):
            try:
                journey = (item.get("journeys") or [{}])[0]
                segments = journey.get("segments") or [{}]
                first_segment = segments[0]
                last_segment = segments[-1]
                transfer_duration = _extract_minutes(
                    journey.get("transferDuration") or item.get("transferDuration")
                )
                if (
                    transfer_duration is not None
                    and transfer_duration > MAX_FLIGHT_TRANSFER_DURATION_MINUTES
                ):
                    continue
                options.append(
                    TransportOption(
                        mode="flight",
                        provider="FlyAI",
                        departure_city=first_segment.get("depCityName") or origin_city,
                        arrival_city=last_segment.get("arrCityName") or destination_city,
                        departure_station=first_segment.get("depStationName"),
                        arrival_station=last_segment.get("arrStationName"),
                        departure_terminal=first_segment.get("depTerm"),
                        arrival_terminal=last_segment.get("arrTerm"),
                        departure_time=_parse_datetime(first_segment.get("depDateTime")),
                        arrival_time=_parse_datetime(last_segment.get("arrDateTime")),
                        duration_minutes=_extract_minutes(
                            item.get("totalDuration")
                            or journey.get("totalDuration")
                            or first_segment.get("duration")
                        ),
                        price=_safe_float(
                            item.get("ticketPrice") or item.get("adultPrice")
                        ),
                        seat_or_class=first_segment.get("seatClassName"),
                        raw_reference=_format_flight_reference(segments),
                        transfer_cities=_extract_transfer_cities(segments),
                        transfer_duration_minutes=transfer_duration,
                        booking_url=item.get("jumpUrl"),
                    )
                )
            except Exception:
                continue
        return options

    def _parse_hotels(self, payload: dict[str, Any]) -> list[Hotel]:
        hotels = []
        for item in ((payload.get("data") or {}).get("itemList") or []):
            try:
                price = _parse_hotel_price(item.get("price"))
                hotels.append(
                    Hotel(
                        name=item["name"],
                        address=item.get("address"),
                        location=_parse_location(item),
                        price_per_night=price["amount"],
                        price_display=price["display"],
                        price_is_starting=price["is_starting"],
                        rating=_safe_float(item.get("score")),
                        distance_desc=item.get("interestsPoi"),
                        hotel_type=item.get("star"),
                        image_url=item.get("mainPic"),
                        booking_url=item.get("detailUrl"),
                    )
                )
            except Exception:
                continue
        return hotels

    def _parse_attractions(self, payload: dict[str, Any]) -> list[Attraction]:
        attractions = []
        for item in ((payload.get("data") or {}).get("itemList") or []):
            try:
                ticket_info = item.get("ticketInfo") or {}
                ticket_price = _safe_float(ticket_info.get("price"))
                attractions.append(
                    Attraction(
                        name=item["name"],
                        address=item.get("address"),
                        location=_parse_location(item),
                        category=item.get("category"),
                        admission_status=_classify_admission_status(
                            free_poi_status=item.get("freePoiStatus"),
                            ticket_price=ticket_price,
                        ),
                        ticket_price=ticket_price,
                        description=ticket_info.get("ticketName")
                        or item.get("description"),
                        image_url=item.get("mainPic"),
                    )
                )
            except Exception:
                continue
        return attractions

    def _parse_restaurants(self, payload: dict[str, Any]) -> list[Restaurant]:
        payload = self._parse_with_llm(
            system_prompt=_build_restaurant_parser_system_prompt(),
            user_prompt=f"请把下面的 FlyAI 餐饮查询结果解析成 JSON：\n{payload}",
        )
        restaurants = []
        for item in payload.get("restaurants", []):
            try:
                restaurants.append(
                    Restaurant(
                        name=item["name"],
                        address=item.get("address"),
                        category=item.get("category"),
                        average_cost=_safe_float(item.get("average_cost")),
                        rating=_safe_float(item.get("rating")),
                        description=item.get("description"),
                    )
                )
            except Exception:
                continue
        return restaurants

    @staticmethod
    def _parse_with_llm(*, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        client = DeepSeekClient()
        if not client.configured:
            return {}
        return client.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=0.1,
        )


def _build_flight_parser_system_prompt() -> str:
    return """
你是结构化数据抽取器。
请把 FlyAI 返回的机票文本解析成 JSON。
只返回 JSON，不要返回解释文字。

JSON 格式：
{
  "flights": [
    {
      "departure_city": "string or null",
      "arrival_city": "string or null",
      "departure_time": "ISO datetime or null",
      "arrival_time": "ISO datetime or null",
      "duration_minutes": "integer or null",
      "price": "number or null",
      "seat_or_class": "string or null",
      "raw_reference": "string or null"
    }
  ]
}
""".strip()


def _build_hotel_parser_system_prompt() -> str:
    return """
你是结构化数据抽取器。
请把 FlyAI 返回的酒店文本解析成 JSON。
只返回 JSON，不要返回解释文字。

JSON 格式：
{
  "hotels": [
    {
      "name": "string",
      "address": "string or null",
      "price_per_night": "number or null",
      "rating": "number or null",
      "distance_desc": "string or null",
      "hotel_type": "string or null",
      "image_url": "string or null",
      "booking_url": "string or null"
    }
  ]
}
""".strip()


def _build_attraction_parser_system_prompt() -> str:
    return """
你是结构化数据抽取器。
请把 FlyAI 返回的景点文本解析成 JSON。
只返回 JSON，不要返回解释文字。

JSON 格式：
{
  "attractions": [
    {
      "name": "string",
      "address": "string or null",
      "category": "string or null",
      "rating": "number or null",
      "ticket_price": "number or null",
      "visit_duration": "integer or null",
      "description": "string or null",
      "image_url": "string or null"
    }
  ]
}
""".strip()


def _build_restaurant_parser_system_prompt() -> str:
    return """
你是结构化数据抽取器。
请把 FlyAI 返回的餐饮文本解析成 JSON。
只返回 JSON，不要返回解释文字。

JSON 格式：
{
  "restaurants": [
    {
      "name": "string",
      "address": "string or null",
      "category": "string or null",
      "average_cost": "number or null",
      "rating": "number or null",
      "description": "string or null"
    }
  ]
}
""".strip()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    normalized = "".join(
        ch for ch in str(value).strip() if ch.isdigit() or ch in {".", "-"}
    )
    if not normalized or normalized in {".", "-", "-."}:
        return None
    try:
        return float(normalized)
    except (TypeError, ValueError):
        return None


def _parse_hotel_price(value: Any) -> dict[str, Any]:
    """Parse FlyAI hotel prices.

    Trial-mode hotel prices may be fuzzy strings such as "¥8x" or "¥1xx".
    In that case the numeric value means the starting price, not an exact quote:
    "¥8x" -> 80 元起, "¥1xx" -> 100 元起.
    """

    if value is None:
        return {"amount": None, "display": "\u4ef7\u683c\u5f85\u786e\u8ba4", "is_starting": False}

    text = str(value).strip()
    fuzzy_match = re.search(r"(\d+)\s*([xX]+)", text)
    if fuzzy_match:
        leading_digits = int(fuzzy_match.group(1))
        x_count = len(fuzzy_match.group(2))
        amount = float(leading_digits * (10**x_count))
        return {
            "amount": amount,
            "display": f"{_format_price_amount(amount)} \u5143\u8d77/\u665a",
            "is_starting": True,
        }

    amount = _safe_float(value)
    if amount is None:
        return {"amount": None, "display": "\u4ef7\u683c\u5f85\u786e\u8ba4", "is_starting": False}

    return {
        "amount": amount,
        "display": f"{_format_price_amount(amount)} \u5143/\u665a",
        "is_starting": False,
    }


def _format_price_amount(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(round(value, 2))


def _classify_admission_status(
    *,
    free_poi_status: Any,
    ticket_price: float | None,
) -> str:
    if ticket_price is not None:
        return "known_paid"

    status = str(free_poi_status or "").upper()
    if status == "FREE":
        return "free"
    if status == "NOT_FREE":
        return "unknown_paid"
    return "unknown"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_location(item: dict[str, Any]) -> Location | None:
    latitude = _safe_float(item.get("latitude"))
    longitude = _safe_float(item.get("longitude"))
    if latitude is None or longitude is None:
        return None
    return Location(latitude=latitude, longitude=longitude)


def _extract_minutes(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value)
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def _format_flight_reference(segments: list[dict[str, Any]]) -> str | None:
    references = [
        item.get("marketingTransportNo")
        for item in segments
        if item.get("marketingTransportNo")
    ]
    return "+".join(str(item) for item in references) if references else None


def _extract_transfer_cities(segments: list[dict[str, Any]]) -> list[str]:
    if len(segments) <= 1:
        return []
    cities = []
    for segment in segments[:-1]:
        city = segment.get("arrCityName")
        if city and city not in cities:
            cities.append(str(city))
    return cities


def _pick_attraction_keyword(preferences: list[str]) -> str | None:
    for item in preferences:
        if item not in {"美食", "餐饮", "小吃"}:
            return item
    return None


def _read_text_file(path: str) -> str:
    with open(path, "rb") as handle:
        return handle.read().decode("utf-8", errors="replace")


def _try_parse_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None
