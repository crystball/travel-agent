from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

from state import WeatherInfo


load_dotenv()


class SeniverseWeatherClient:
    """Minimal Seniverse weather API client."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        language: str | None = None,
        unit: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key or os.getenv("SENIVERSE_API_KEY")
        self.language = language or os.getenv("SENIVERSE_LANGUAGE") or "zh-Hans"
        self.unit = unit or os.getenv("SENIVERSE_UNIT") or "c"
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def get_daily_forecast(self, city: str, days: int = 3) -> WeatherInfo | None:
        return self.get_daily_forecast_from(city=city, start=0, days=days)

    def get_daily_forecast_from(
        self,
        *,
        city: str,
        start: int = 0,
        days: int = 3,
    ) -> WeatherInfo | None:
        if not self.configured:
            return None

        payload = self._get(
            "https://api.seniverse.com/v3/weather/daily.json",
            params={
                "key": self.api_key,
                "location": city,
                "language": self.language,
                "unit": self.unit,
                "start": max(0, start),
                "days": max(1, min(days, 15)),
            },
        )
        results = payload.get("results", [])
        if not results:
            return None

        result = results[0]
        location = result.get("location", {})
        daily = result.get("daily", [])
        normalized_daily = [
            {
                "date": item.get("date"),
                "text_day": item.get("text_day"),
                "text_night": item.get("text_night"),
                "high": item.get("high"),
                "low": item.get("low"),
            }
            for item in daily
        ]
        forecast = [
            (
                f"{item.get('date')}: "
                f"{item.get('text_day')}/{item.get('text_night')} "
                f"{item.get('low')}~{item.get('high')}°C"
            )
            for item in daily
        ]

        return WeatherInfo(
            city=location.get("name", city),
            summary=forecast[0] if forecast else None,
            forecast=forecast,
            daily=normalized_daily,
            last_update=result.get("last_update"),
        )

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception:
            return {}
