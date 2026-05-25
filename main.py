from __future__ import annotations

import argparse
import sys
from typing import Any

from pydantic import BaseModel

from html_renderer import render_travel_guide_html
from workflow import run_workflow


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Travel Planner core workflow runner")
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Natural-language travel request",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full final state as JSON-compatible data",
    )
    parser.add_argument(
        "--html",
        nargs="?",
        const="travel_guide.html",
        help="Render a static HTML travel guide. Optionally provide output path.",
    )
    args = parser.parse_args()

    final_state = run_workflow(args.input)

    if args.html:
        output_path = render_travel_guide_html(final_state, args.html)
        print(f"HTML旅行指南已生成: {output_path.resolve()}")

    if args.json:
        print(_to_plain_data(final_state))
        return

    _print_summary(final_state)


def _print_summary(state: dict[str, Any]) -> None:
    status = state.get("status", "unknown")
    print(f"状态: {status}")

    requirement = state.get("requirement")
    if requirement is not None:
        print("\n[需求解析]")
        print(f"出发地: {requirement.origin_city}")
        print(f"目的地: {requirement.destination_city}")
        print(f"日期: {requirement.start_date} -> {requirement.end_date}")
        print(f"天数: {requirement.days}")
        print(f"人数: {requirement.travelers}")
        print(f"预算: {requirement.budget}")
        print(f"偏好: {'、'.join(requirement.preferences) or '无'}")

    if state.get("warnings"):
        print("\n[提醒]")
        for warning in state["warnings"]:
            print(f"- {warning}")

    if status in {"partial", "failed"}:
        return

    attraction_result = state.get("attraction_result")
    if attraction_result is not None:
        print("\n[景点推荐]")
        for index, item in enumerate(attraction_result.recommended_attractions, start=1):
            print(f"{index}. {item.name}")
            if item.image_url:
                print(f"   图片: ![{item.name}]({item.image_url})")
            print(f"   推荐理由: {item.reason}")
            if item.description:
                print(f"   简介: {item.description}")
            if item.address:
                print(f"   地址: {item.address}")
            print(f"   门票: {_format_admission(item)}")

    transportation_result = state.get("transportation_result")
    if transportation_result is not None:
        print("\n[交通规划]")
        if transportation_result.recommended_plan:
            plan = transportation_result.recommended_plan
            all_options = [plan, *transportation_result.alternative_plans]
            print("推荐交通方案:")
            for option in all_options:
                _print_transport_plan(f"- {_transport_mode_label(option.outbound.mode)}", option, indent="  ")
        else:
            print("当前没有可用的推荐交通方案。")

    booking_result = state.get("booking_result")
    if booking_result is not None:
        print("\n[酒店推荐]")
        for hotel in booking_result.recommended_hotels:
            price_text = hotel.price_display or _format_hotel_price(hotel.price_per_night)
            print(f"- {hotel.name} / {price_text}")
            if hotel.distance_to_anchor_km is not None:
                print(f"  距首日景点约: {hotel.distance_to_anchor_km} km")
            if hotel.distance_desc:
                print(f"  位置参考: {hotel.distance_desc}")
            if hotel.address:
                print(f"  地址: {hotel.address}")
            if hotel.image_url:
                print(f"  图片: ![{hotel.name}]({hotel.image_url})")
            if hotel.booking_url:
                print(f"  预订链接: {hotel.booking_url}")

    budget_result = state.get("budget_result")
    if budget_result is not None:
        print("\n[预算分析]")
        print(f"已计入核心费用: {budget_result.total_cost}")
        print(f"预算组成: {_format_budget_composition(state)}")
        print(f"剩余预算: {budget_result.remaining_budget}")
        for suggestion in budget_result.suggestions:
            print(f"- {suggestion}")

    itinerary_result = state.get("itinerary_result")
    if itinerary_result is not None:
        print("\n[最终行程]")
        print(itinerary_result.summary)
        weather_note = _format_weather_note(state)
        if weather_note:
            print(f"天气提示: {weather_note}")
        for day in itinerary_result.days:
            print(f"\n{day.date or ''} {day.theme or ''}".strip())
            if getattr(day, "weather", None):
                print(f"  天气: {day.weather}")
            print(f"  上午: {'；'.join(day.morning)}")
            if day.afternoon:
                print(f"  下午: {'；'.join(day.afternoon)}")
            if getattr(day, "transfer_notes", None):
                print("  交通参考:")
                for note in day.transfer_notes:
                    print(f"    - {note}")






def _format_admission(item: Any) -> str:
    status = getattr(item, "admission_status", None)
    ticket_price = getattr(item, "ticket_price", None)
    if status == "free":
        return "\u514d\u8d39"
    if status == "known_paid" and ticket_price is not None:
        return f"\u7ea6 {ticket_price} \u5143"
    if status == "unknown_paid":
        return "\u6536\u8d39\uff0c\u4ef7\u683c\u5f85\u786e\u8ba4"
    return "\u5f85\u786e\u8ba4"


def _format_hotel_price(value: Any) -> str:
    if value is None:
        return "\u4ef7\u683c\u5f85\u786e\u8ba4"
    if isinstance(value, (int, float)) and float(value).is_integer():
        return f"{int(value)} \u5143/\u665a"
    return f"{value} \u5143/\u665a"


def _format_budget_composition(state: dict[str, Any]) -> str:
    budget_result = state.get("budget_result")
    transportation_result = state.get("transportation_result")
    booking_result = state.get("booking_result")
    breakdown = getattr(budget_result, "cost_breakdown", {}) or {}

    transport_plan = (
        getattr(transportation_result, "recommended_plan", None)
        if transportation_result is not None
        else None
    )
    transport_label = (
        _transport_mode_label(transport_plan.outbound.mode)
        if transport_plan is not None
        else "\u4ea4\u901a\u65b9\u6848\u5f85\u786e\u8ba4"
    )
    transport_cost = breakdown.get("transport", 0)

    hotel = (
        booking_result.recommended_hotels[0]
        if booking_result is not None and booking_result.recommended_hotels
        else None
    )
    hotel_label = hotel.name if hotel is not None else "\u9152\u5e97\u5f85\u786e\u8ba4"
    hotel_cost = breakdown.get("hotel", 0)
    ticket_cost = breakdown.get("tickets", 0)

    return (
        f"\u4ea4\u901a\uff08{transport_label}\uff09\u7ea6 {transport_cost} \u5143 + "
        f"\u9152\u5e97\uff08{hotel_label}\uff09\u7ea6 {hotel_cost} \u5143 + "
        f"\u5df2\u77e5\u666f\u70b9\u95e8\u7968\u7ea6 {ticket_cost} \u5143"
    )


def _format_weather_note(state: dict[str, Any]) -> str | None:
    attraction_result = state.get("attraction_result")
    weather = getattr(attraction_result, "weather", None) if attraction_result is not None else None
    if weather is None:
        return None
    if not getattr(weather, "is_available", True):
        return getattr(weather, "unavailable_reason", None)
    return None


def _print_transport_plan(label: str, plan: Any, indent: str = "") -> None:
    outbound = plan.outbound
    unknown_ref = "\u672a\u77e5\u73ed\u6b21"
    unknown_price = "\u4ef7\u683c\u5f85\u786e\u8ba4"
    unknown_time = "\u65f6\u95f4\u5f85\u786e\u8ba4"
    print(f"{indent}{label}:")
    _print_transport_option("\u53bb\u7a0b", outbound, indent, unknown_ref, unknown_price)
    print(
        f"{indent}    \u51fa\u53d1: {_format_datetime(outbound.departure_time) or unknown_time}"
        f" / \u5230\u8fbe: {_format_datetime(outbound.arrival_time) or unknown_time}"
    )
    if plan.return_trip:
        return_trip = plan.return_trip
        _print_transport_option("\u8fd4\u7a0b", return_trip, indent, unknown_ref, unknown_price)
        print(
            f"{indent}    \u51fa\u53d1: {_format_datetime(return_trip.departure_time) or unknown_time}"
            f" / \u5230\u8fbe: {_format_datetime(return_trip.arrival_time) or unknown_time}"
        )
    print(f"{indent}  \u9884\u8ba1\u4ea4\u901a\u8d39\u7528: {plan.total_price}")
    if plan.total_duration_minutes is not None:
        print(f"{indent}  \u884c\u7a0b\u8017\u65f6: {plan.total_duration_minutes} \u5206\u949f")
    if plan.reminders:
        print(f"{indent}  \u63d0\u9192:")
        for reminder in plan.reminders:
            print(f"{indent}    - {reminder}")


def _print_transport_option(
    label: str,
    option: Any,
    indent: str,
    unknown_ref: str,
    unknown_price: str,
) -> None:
    if option.mode == "flight":
        route = (
            f"{_format_station(option.departure_station, option.departure_terminal)}"
            f" -> {_format_station(option.arrival_station, option.arrival_terminal)}"
        )
    else:
        route = f"{option.departure_city} -> {option.arrival_city}"
    print(
        f"{indent}  {label}: {_transport_mode_label(option.mode)} / "
        f"{route}"
        f" / {option.raw_reference or unknown_ref}"
        f" / {option.price if option.price is not None else unknown_price} \u5143"
    )
    if option.booking_url:
        print(f"{indent}    \u8ba2\u7968\u94fe\u63a5: {option.booking_url}")


def _format_station(station: Any, terminal: Any) -> str:
    station_text = str(station) if station else "\u673a\u573a\u5f85\u786e\u8ba4"
    return f"{station_text}{terminal}" if terminal else station_text


def _transport_mode_label(mode: str) -> str:
    return {"train": "\u9ad8\u94c1/\u52a8\u8f66", "flight": "\u98de\u673a"}.get(mode, mode)


def _format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M") if hasattr(value, "strftime") else str(value)


def _to_plain_data(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _to_plain_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain_data(item) for item in value]
    return value


if __name__ == "__main__":
    main()
