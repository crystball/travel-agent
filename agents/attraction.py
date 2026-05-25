from __future__ import annotations

import os

from flyai_client import FlyAIClient
from llm_client import DeepSeekClient
from state import (
    AgentError,
    Attraction,
    AttractionRecommendation,
    AttractionResult,
    Restaurant,
    TravelPlanState,
)
from weather_client import SeniverseWeatherClient
from timing_utils import attraction_llm_enabled, timed_step


def build_attraction_result(state: TravelPlanState) -> AttractionResult:
    requirement = state["requirement"]
    routing_info = state["routing_info"]
    flyai_client = FlyAIClient()
    weather_client = SeniverseWeatherClient()

    attractions = flyai_client.search_attractions(
        requirement.destination_city or "",
        requirement.preferences,
    )
    restaurants: list[Restaurant] = []
    weather = _get_trip_weather(
        weather_client=weather_client,
        destination=requirement.destination_city or "",
        days_until_departure=routing_info.days_until_departure,
        trip_days=requirement.days or 1,
    )

    notes: list[str] = []
    source_summary: list[str] = []
    is_fallback = False

    if attractions:
        source_summary.append("FlyAI 景点搜索")
    else:
        attractions = _fallback_attractions(requirement.destination_city or "目的地")
        notes.append("未获取到真实景点数据，已使用兜底景点占位。")
        is_fallback = True

    notes.append(
        "\u5f53\u524d\u672a\u63a5\u5165\u53ef\u9760\u7684\u9910\u5385\u7ed3\u6784\u5316\u6570\u636e\u6e90\uff0c"
        "\u9910\u996e\u5b89\u6392\u4ec5\u63d0\u4f9b\u7c7b\u578b/\u533a\u57df\u5efa\u8bae\uff0c"
        "\u9910\u996e\u9884\u7b97\u4f7f\u7528\u7ecf\u9a8c\u4f30\u7b97\u3002"
    )

    if weather and weather.is_available:
        source_summary.append("心知天气")
    elif weather and not weather.is_available:
        notes.append(weather.unavailable_reason or "行程日期超出天气查询范围。")
    else:
        notes.append("当前未获取到有效天气，景点推荐未结合实时天气调整。")

    recommended = _build_recommendations_with_llm(
        attractions=attractions,
        restaurants=restaurants,
        weather=weather.model_dump(mode="json") if weather and weather.is_available else None,
        preferences=requirement.preferences,
        days=requirement.days or 1,
    )
    if not recommended:
        recommended = [
            AttractionRecommendation(
                name=item.name,
                reason=_build_recommendation_reason(item, requirement.preferences),
            )
            for item in _rank_attractions(attractions)[
                : max((requirement.days or 1) * 2, 3)
            ]
        ]
    recommended = _enrich_recommendations(
        recommended,
        attractions,
        preferences=requirement.preferences,
    )

    return AttractionResult(
        attractions=attractions,
        restaurants=restaurants,
        weather=weather,
        recommended_attractions=recommended,
        notes=notes,
        source_summary=source_summary,
        is_fallback=is_fallback,
    )


def attraction_node(state: TravelPlanState) -> TravelPlanState:
    with timed_step("attraction"):
        try:
            return {"attraction_result": build_attraction_result(state)}
        except Exception as exc:
            destination = state["requirement"].destination_city or "目的地"
            return {
                "attraction_result": AttractionResult(
                    attractions=_fallback_attractions(destination),
                    restaurants=[],
                    recommended_attractions=[
                        AttractionRecommendation(
                            name=f"{destination}核心景点",
                            reason="真实数据获取失败，使用兜底建议。",
                        )
                    ],
                    notes=["景点模块执行失败，已启用兜底结果。"],
                    is_fallback=True,
                ),
                "errors": [
                    AgentError(
                        agent_name="attraction",
                        error_type=type(exc).__name__,
                        message=str(exc),
                        recoverable=True,
                        fallback_used=True,
                    )
                ],
        }


def _get_trip_weather(
    *,
    weather_client: SeniverseWeatherClient,
    destination: str,
    days_until_departure: int | None,
    trip_days: int,
) -> object | None:
    if days_until_departure is None or days_until_departure < 0:
        return None

    max_forecast_days = _weather_window_days()
    trip_days = max(1, trip_days)
    if days_until_departure + trip_days > max_forecast_days:
        return _weather_unavailable(
            destination,
            f"行程日期超出天气查询范围：当前最多可查询未来{max_forecast_days}天内且需覆盖完整行程，因此暂不展示天气。",
        )

    weather = weather_client.get_daily_forecast_from(
        city=destination,
        start=days_until_departure,
        days=trip_days,
    )
    if weather is None:
        return None
    if len(weather.daily) < trip_days:
        return _weather_unavailable(
            destination,
            "天气接口未返回完整行程日期的预报，因此暂不展示天气。",
        )
    return weather


def _weather_unavailable(city: str, reason: str):
    from state import WeatherInfo

    return WeatherInfo(
        city=city,
        is_available=False,
        unavailable_reason=reason,
    )


def _weather_window_days() -> int:
    try:
        return max(1, int(os.getenv("SENIVERSE_MAX_FORECAST_DAYS", "14")))
    except ValueError:
        return 14

def _rank_attractions(attractions: list[Attraction]) -> list[Attraction]:
    return sorted(attractions, key=lambda item: item.rating or 0, reverse=True)


def _build_recommendation_reason(
    attraction: Attraction, preferences: list[str]
) -> str:
    parts: list[str] = []

    if attraction.category:
        parts.append(f"\u5c5e\u4e8e{attraction.category}\u7c7b\u666f\u70b9")

    if preferences:
        matched = [item for item in preferences if item and item in _attraction_text(attraction)]
        separator = "\u3001"
        if matched:
            matched_text = separator.join(matched)
            parts.append(f"\u4e0e{matched_text}\u504f\u597d\u76f4\u63a5\u76f8\u5173")
        else:
            preference_text = separator.join(preferences)
            parts.append(f"\u53ef\u8865\u5145{preference_text}\u4e3b\u9898\u4f53\u9a8c")

    if attraction.admission_status == "free":
        parts.append("\u514d\u8d39\u5f00\u653e\uff0c\u9002\u5408\u4f5c\u4e3a\u8f7b\u677e\u6e38\u89c8\u6216\u6563\u6b65\u5b89\u6392")
    elif attraction.admission_status == "known_paid" and attraction.ticket_price is not None:
        parts.append(f"\u5df2\u6709\u660e\u786e\u7968\u4ef7\u7ea6{attraction.ticket_price}\u5143\uff0c\u4fbf\u4e8e\u63d0\u524d\u63a7\u5236\u9884\u7b97")
    elif attraction.admission_status == "unknown_paid":
        parts.append("\u5c5e\u4e8e\u6536\u8d39\u666f\u70b9\u4f46\u4ef7\u683c\u5f85\u786e\u8ba4\uff0c\u9002\u5408\u5728\u9884\u7b97\u9884\u7559\u540e\u5b89\u6392")

    highlight = _extract_reason_highlight(attraction.description)
    if highlight:
        parts.append(highlight)

    if not parts:
        return "\u9002\u5408\u4f5c\u4e3a\u672c\u6b21\u65c5\u884c\u7684\u4ee3\u8868\u6027\u666f\u70b9\u3002"

    return "\uff1b".join(parts[:3]) + "\u3002"


def _enrich_recommendations(
    recommendations: list[AttractionRecommendation],
    attractions: list[Attraction],
    preferences: list[str],
) -> list[AttractionRecommendation]:
    attraction_by_name = {item.name: item for item in attractions}
    enriched: list[AttractionRecommendation] = []
    for recommendation in recommendations:
        attraction = attraction_by_name.get(recommendation.name)
        if attraction is None:
            enriched.append(recommendation)
            continue
        enriched.append(
            recommendation.model_copy(
                update={
                    "reason": _build_recommendation_reason(attraction, preferences),
                    "description": _shorten_text(attraction.description),
                    "full_description": _normalize_text(attraction.description),
                    "image_url": attraction.image_url,
                    "address": attraction.address,
                    "admission_status": attraction.admission_status,
                    "ticket_price": attraction.ticket_price,
                }
            )
        )
    return enriched


def _attraction_text(attraction: Attraction) -> str:
    return " ".join(
        item
        for item in [attraction.name, attraction.category, attraction.description]
        if item
    )


def _extract_reason_highlight(description: str | None, max_length: int = 42) -> str | None:
    normalized = _normalize_text(description)
    if not normalized:
        return None
    first_sentence = normalized.split("\u3002", maxsplit=1)[0].strip()
    if not first_sentence:
        return None
    if len(first_sentence) > max_length:
        first_sentence = first_sentence[:max_length].rstrip() + "..."
    return first_sentence


def _normalize_text(text: str | None) -> str | None:
    if not text:
        return None
    return " ".join(text.split())


def _shorten_text(text: str | None, max_length: int = 120) -> str | None:
    normalized = _normalize_text(text)
    if not normalized:
        return None
    if len(normalized) <= max_length:
        return normalized
    return normalized[:max_length].rstrip() + "..."


def _fallback_attractions(destination: str) -> list[Attraction]:
    return [
        Attraction(
            name=f"{destination}核心景点",
            category="综合推荐",
            description="等待接入真实景点数据后替换。",
        )
    ]


def _fallback_restaurants(destination: str) -> list[Restaurant]:
    return [
        Restaurant(
            name=f"{destination}本地特色餐饮",
            category="本地美食",
            description="等待接入真实餐饮数据后替换。",
        )
    ]


def _build_recommendations_with_llm(
    *,
    attractions: list[Attraction],
    restaurants: list[Restaurant],
    weather: dict | None,
    preferences: list[str],
    days: int,
) -> list[AttractionRecommendation]:
    if not attraction_llm_enabled():
        return []

    client = DeepSeekClient()
    if not client.configured:
        return []

    try:
        payload = client.chat_json(
            system_prompt=_build_system_prompt(),
            user_prompt=_build_user_prompt(
                attractions=attractions,
                restaurants=restaurants,
                weather=weather,
                preferences=preferences,
                days=days,
            ),
            temperature=0.2,
        )
        raw_recommendations = payload.get("recommended_attractions", [])
        recommendations = [
            AttractionRecommendation(**item)
            for item in raw_recommendations
            if isinstance(item, dict)
        ]
        return recommendations
    except Exception:
        return []


def _build_system_prompt() -> str:
    return """
你是旅行景点推荐助手。
请基于给定的真实景点、餐厅、天气和用户偏好，输出景点推荐 JSON。

要求：
1. 只返回 JSON，不要返回解释文字。
2. 只能从给定 attractions 中挑选，不要编造新景点。
3. 推荐数量应与旅行天数匹配，通常每天 1 到 2 个核心景点。
4. 如果给出了天气信息，需要在理由中体现天气影响。
5. 理由应结合用户偏好，而不是只复述评分。

JSON 格式：
{
  "recommended_attractions": [
    {
      "name": "string",
      "reason": "string"
    }
  ]
}
""".strip()


def _build_user_prompt(
    *,
    attractions: list[Attraction],
    restaurants: list[Restaurant],
    weather: dict | None,
    preferences: list[str],
    days: int,
) -> str:
    attraction_payload = [item.model_dump(mode="json") for item in attractions]
    restaurant_payload = [item.model_dump(mode="json") for item in restaurants]
    return f"""
请基于以下信息生成景点推荐：

days = {days}
preferences = {preferences}
weather = {weather}
attractions = {attraction_payload}
restaurants = {restaurant_payload}
""".strip()
