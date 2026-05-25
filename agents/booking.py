from __future__ import annotations

from math import ceil

from geo_utils import distance_km, has_location
from state import AgentError, Attraction, BookingResult, Hotel, Location, TravelPlanState
from timing_utils import timed_step
from transport_clients import TransportClients


def build_booking_result(state: TravelPlanState) -> BookingResult:
    requirement = state["requirement"]
    routing_info = state["routing_info"]
    clients = TransportClients()

    hotels: list[Hotel] = []
    source_summary: list[str] = []
    limitations: list[str] = []
    is_fallback = False
    first_day_attractions = _pick_first_day_attractions(state)
    first_day_anchor = _build_location_anchor(first_day_attractions)
    hotel_search_poi = _pick_hotel_search_poi(
        preferences=requirement.preferences,
        first_day_attractions=first_day_attractions,
    )

    if (
        routing_info.hotel_query_available
        and requirement.start_date
        and requirement.end_date
    ):
        hotels = clients.query_flyai_hotels(
            requirement.destination_city or "",
            requirement.start_date,
            requirement.end_date,
            requirement.hotel_preference,
            poi_name=hotel_search_poi,
        )
        source_summary.append("FlyAI hotel search")

    if not hotels:
        hotels = _fallback_hotels(
            requirement.destination_city or "目的地",
            requirement.hotel_preference,
        )
        limitations.append("未获取到真实酒店数据，已使用兜底住宿建议。")
        is_fallback = True

    hotels = _annotate_hotel_distances(hotels, first_day_anchor)
    recommended_hotels = _recommend_hotels(hotels)
    selection_reason = (
        "优先选择靠近首日景点的住宿，并尽量覆盖不同价格档位，方便用户在位置与预算之间自行取舍。"
    )
    if first_day_attractions:
        search_strategy = [
            "围绕首日景点选择住宿",
            "优先按酒店到首日景点簇的距离排序",
            "最多推荐三个不同价位的候选",
        ]
    else:
        search_strategy = ["按城市搜索", "按价格档位去重", "最多推荐三个候选"]
        limitations.append("缺少可用景点坐标，酒店推荐暂未结合首日景点距离。")

    return BookingResult(
        hotels=hotels,
        recommended_hotels=recommended_hotels,
        search_strategy=search_strategy,
        selection_reason=selection_reason,
        source_summary=source_summary,
        limitations=limitations,
        is_fallback=is_fallback,
    )


def booking_node(state: TravelPlanState) -> TravelPlanState:
    with timed_step("booking"):
        try:
            return {"booking_result": build_booking_result(state)}
        except Exception as exc:
            destination = state["requirement"].destination_city or "目的地"
            return {
                "booking_result": BookingResult(
                    hotels=_fallback_hotels(destination, None),
                    recommended_hotels=_fallback_hotels(destination, None),
                    limitations=["酒店模块执行失败，已启用兜底住宿建议。"],
                    is_fallback=True,
                ),
                "errors": [
                    AgentError(
                        agent_name="booking",
                        error_type=type(exc).__name__,
                        message=str(exc),
                        recoverable=True,
                        fallback_used=True,
                    )
                ],
            }


def estimated_room_count(travelers: int) -> int:
    return max(1, ceil(travelers / 2))


def _rank_hotels(hotels: list[Hotel]) -> list[Hotel]:
    return sorted(
        hotels,
        key=lambda item: (
            item.distance_to_anchor_km
            if item.distance_to_anchor_km is not None
            else float("inf"),
            -(item.rating or 0),
            item.price_per_night if item.price_per_night is not None else float("inf"),
        ),
    )


def _recommend_hotels(hotels: list[Hotel]) -> list[Hotel]:
    ranked = _rank_hotels(hotels)
    selected: list[Hotel] = []
    selected_names: set[str] = set()
    used_price_bands: set[str] = set()

    for hotel in ranked:
        band = _price_band(hotel)
        if band in used_price_bands:
            continue
        selected.append(hotel)
        selected_names.add(hotel.name)
        used_price_bands.add(band)
        if len(selected) >= 3:
            return selected

    for hotel in ranked:
        if hotel.name in selected_names:
            continue
        selected.append(hotel)
        selected_names.add(hotel.name)
        if len(selected) >= 3:
            break

    return selected


def _price_band(hotel: Hotel) -> str:
    price = hotel.price_per_night
    if price is None:
        return "unknown"
    if price < 200:
        return "budget"
    if price < 400:
        return "mid"
    return "premium"


def _pick_first_day_attractions(state: TravelPlanState) -> list[Attraction]:
    attraction_result = state.get("attraction_result")
    requirement = state["requirement"]
    if attraction_result is None:
        return []

    attraction_by_name = {item.name: item for item in attraction_result.attractions}
    preferred_names = [item.name for item in attraction_result.recommended_attractions]
    ordered = [
        attraction_by_name[name]
        for name in preferred_names
        if name in attraction_by_name
    ]
    if not ordered:
        ordered = attraction_result.attractions[:]
    if not ordered:
        return []

    day_count = max(requirement.days or 1, 1)
    target_group_size = max(1, (len(ordered) + day_count - 1) // day_count)
    first_day = [ordered.pop(0)]
    while ordered and len(first_day) < target_group_size:
        first_day.append(_pop_nearest_attraction(first_day, ordered))
    return first_day


def _pop_nearest_attraction(
    group: list[Attraction],
    candidates: list[Attraction],
) -> Attraction:
    if not group or not any(has_location(item) for item in group):
        return candidates.pop(0)

    best_index = 0
    best_distance = float("inf")
    for index, candidate in enumerate(candidates):
        candidate_distance = _distance_to_group(candidate, group)
        if candidate_distance < best_distance:
            best_index = index
            best_distance = candidate_distance
    return candidates.pop(best_index)


def _distance_to_group(candidate: Attraction, group: list[Attraction]) -> float:
    if not has_location(candidate):
        return float("inf")

    distances = [
        distance_km(candidate.location, item.location)
        for item in group
        if has_location(item)
    ]
    return min(distances) if distances else float("inf")


def _build_location_anchor(attractions: list[Attraction]) -> Location | None:
    locations = [item.location for item in attractions if has_location(item)]
    if not locations:
        return None
    return Location(
        latitude=sum(item.latitude or 0 for item in locations) / len(locations),
        longitude=sum(item.longitude or 0 for item in locations) / len(locations),
    )


def _annotate_hotel_distances(
    hotels: list[Hotel],
    anchor: Location | None,
) -> list[Hotel]:
    if anchor is None:
        return hotels
    annotated: list[Hotel] = []
    for hotel in hotels:
        if has_location(hotel):
            distance = round(distance_km(hotel.location, anchor), 2)
            annotated.append(hotel.model_copy(update={"distance_to_anchor_km": distance}))
        else:
            annotated.append(hotel)
    return annotated


def _pick_hotel_search_poi(
    *,
    preferences: list[str],
    first_day_attractions: list[Attraction],
) -> str | None:
    attraction_text = " ".join(
        item
        for attraction in first_day_attractions
        for item in [attraction.name, attraction.address, attraction.description]
        if item
    )
    for preference in preferences:
        if preference and preference in attraction_text:
            return preference
    return first_day_attractions[0].name if first_day_attractions else None


def _fallback_hotels(destination: str, preference: str | None) -> list[Hotel]:
    default_price = {
        "经济型": 260,
        "舒适型": 420,
        "豪华型": 800,
    }.get(preference, 380)
    return [
        Hotel(
            name=f"{destination}参考酒店",
            price_per_night=default_price,
            price_display=f"{default_price} 元/晚",
            hotel_type=preference or "参考型",
        )
    ]
