from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any


def render_travel_guide_html(state: dict[str, Any], output_path: str | Path) -> Path:
    output = Path(output_path)
    html = _build_html(state)
    output.write_text(html, encoding="utf-8")
    return output


def _build_html(state: dict[str, Any]) -> str:
    requirement = state.get("requirement")
    destination = getattr(requirement, "destination_city", None) or "目的地"
    title = f"{destination}旅行指南"

    sections = [
        _render_header(state),
        _render_requirement(state),
        _render_weather(state),
        _render_attractions(state),
        _render_transportation(state),
        _render_hotels(state),
        _render_budget(state),
        _render_itinerary(state),
    ]

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #f6f7fb;
      --card: #ffffff;
      --text: #1f2937;
      --muted: #6b7280;
      --line: #e5e7eb;
      --primary: #2563eb;
      --primary-soft: #dbeafe;
      --accent: #16a34a;
      --warn: #f59e0b;
      --shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
    }}

    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(180deg, #eef4ff 0%, var(--bg) 280px);
      color: var(--text);
      line-height: 1.65;
    }}

    .page {{
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 32px 0 56px;
    }}

    .hero {{
      padding: 34px;
      border-radius: 28px;
      background: rgba(255, 255, 255, 0.82);
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
      margin-bottom: 24px;
    }}

    .eyebrow {{
      display: inline-flex;
      gap: 8px;
      align-items: center;
      padding: 6px 12px;
      border-radius: 999px;
      background: var(--primary-soft);
      color: var(--primary);
      font-size: 13px;
      font-weight: 700;
    }}

    h1 {{
      margin: 16px 0 10px;
      font-size: clamp(32px, 5vw, 52px);
      line-height: 1.1;
      letter-spacing: -0.04em;
    }}

    h2 {{
      margin: 0 0 18px;
      font-size: 24px;
      letter-spacing: -0.02em;
    }}

    h3 {{
      margin: 0 0 8px;
      font-size: 18px;
    }}

    .subtitle {{
      max-width: 760px;
      color: var(--muted);
      margin: 0;
      font-size: 16px;
    }}

    .section {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 24px;
      box-shadow: 0 10px 28px rgba(15, 23, 42, 0.05);
      margin-top: 18px;
    }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
    }}

    .card {{
      border: 1px solid var(--line);
      border-radius: 18px;
      background: #fff;
      overflow: hidden;
    }}

    .card-body {{ padding: 16px; }}
    .cover {{
      width: 100%;
      height: 180px;
      object-fit: cover;
      display: block;
      background: #eef2f7;
    }}

    .meta {{
      color: var(--muted);
      font-size: 14px;
      margin: 4px 0;
    }}

    .tag {{
      display: inline-flex;
      align-items: center;
      padding: 3px 9px;
      border-radius: 999px;
      background: #f3f4f6;
      color: #374151;
      font-size: 12px;
      margin: 2px 4px 2px 0;
    }}

    .tag.primary {{ background: var(--primary-soft); color: var(--primary); }}
    .tag.green {{ background: #dcfce7; color: #15803d; }}
    .tag.warn {{ background: #fef3c7; color: #b45309; }}

    .list {{
      display: grid;
      gap: 12px;
    }}

    .row {{
      padding: 14px 16px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: #fff;
    }}

    .two-col {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }}

    .route {{
      margin-top: 8px;
      padding: 10px 12px;
      border-radius: 14px;
      background: #f8fafc;
      color: #334155;
      font-size: 14px;
    }}

    .timeline {{
      position: relative;
      display: grid;
      gap: 14px;
    }}

    .day {{
      border-left: 4px solid var(--primary);
      padding: 2px 0 2px 16px;
    }}

    .time-block {{
      margin-top: 8px;
      padding: 12px 14px;
      border-radius: 14px;
      background: #f8fafc;
    }}

    .button {{
      display: inline-flex;
      text-decoration: none;
      color: #fff;
      background: var(--primary);
      border-radius: 999px;
      padding: 7px 12px;
      font-size: 13px;
      font-weight: 700;
      margin-top: 8px;
    }}

    details {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 14px;
    }}

    summary {{
      cursor: pointer;
      color: var(--primary);
      font-weight: 700;
    }}

    .empty {{
      color: var(--muted);
      padding: 18px;
      border: 1px dashed var(--line);
      border-radius: 16px;
      background: #fafafa;
    }}

    @media print {{
      body {{ background: #fff; }}
      .section, .hero {{ box-shadow: none; }}
      .button {{ color: var(--primary); background: transparent; padding: 0; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    {''.join(sections)}
  </main>
</body>
</html>
"""


def _render_header(state: dict[str, Any]) -> str:
    requirement = state.get("requirement")
    destination = getattr(requirement, "destination_city", None) or "目的地"
    start_date = getattr(requirement, "start_date", None)
    end_date = getattr(requirement, "end_date", None)
    days = getattr(requirement, "days", None)
    subtitle_parts = []
    if start_date and end_date:
        subtitle_parts.append(f"{start_date} 至 {end_date}")
    if days:
        subtitle_parts.append(f"{days} 天游")
    if getattr(requirement, "travelers", None):
        subtitle_parts.append(f"{requirement.travelers} 人出行")

    return f"""
<section class="hero">
  <div class="eyebrow">AI Travel Guide</div>
  <h1>{escape(destination)}旅行指南</h1>
  <p class="subtitle">{escape(' · '.join(subtitle_parts) or '基于当前可用交通、酒店、景点数据生成。')}</p>
</section>
"""


def _render_requirement(state: dict[str, Any]) -> str:
    requirement = state.get("requirement")
    if requirement is None:
        return ""
    preferences = "、".join(getattr(requirement, "preferences", []) or []) or "无"
    return f"""
<section class="section">
  <h2>需求概览</h2>
  <div class="grid">
    <div class="row"><strong>出发地</strong><div class="meta">{escape(getattr(requirement, 'origin_city', None) or '-')}</div></div>
    <div class="row"><strong>目的地</strong><div class="meta">{escape(getattr(requirement, 'destination_city', None) or '-')}</div></div>
    <div class="row"><strong>预算</strong><div class="meta">{escape(str(getattr(requirement, 'budget', None) or '-'))}</div></div>
    <div class="row"><strong>偏好</strong><div class="meta">{escape(preferences)}</div></div>
  </div>
</section>
"""


def _render_attractions(state: dict[str, Any]) -> str:
    result = state.get("attraction_result")
    if result is None:
        return ""
    items = getattr(result, "recommended_attractions", []) or []
    if not items:
        return _section_empty("景点推荐", "暂无景点推荐。")

    cards = []
    for item in items:
        image = _image(getattr(item, "image_url", None), getattr(item, "name", "景点"))
        admission = _format_admission(item)
        description = escape(getattr(item, "description", None) or "")
        full_description = getattr(item, "full_description", None)
        details = ""
        if full_description and full_description != getattr(item, "description", None):
            details = f"<details><summary>查看完整简介</summary><p>{escape(full_description)}</p></details>"
        cards.append(
            f"""
<article class="card">
  {image}
  <div class="card-body">
    <h3>{escape(getattr(item, 'name', '景点'))}</h3>
    <span class="tag primary">{escape(admission)}</span>
    <p class="meta">{escape(getattr(item, 'reason', None) or '')}</p>
    <p>{description}</p>
    {details}
    <p class="meta">{escape(getattr(item, 'address', None) or '')}</p>
  </div>
</article>
"""
        )

    return f"""
<section class="section">
  <h2>景点推荐</h2>
  <div class="grid">{''.join(cards)}</div>
</section>
"""


def _render_weather(state: dict[str, Any]) -> str:
    attraction_result = state.get("attraction_result")
    weather = getattr(attraction_result, "weather", None) if attraction_result is not None else None
    if weather is None:
        return ""
    if not getattr(weather, "is_available", True):
        reason = getattr(weather, "unavailable_reason", None) or "行程日期超出天气查询范围，暂不展示天气。"
        return f"""
<section class="section">
  <h2>天气预报</h2>
  <div class="empty">{escape(reason)}</div>
</section>
"""

    daily = getattr(weather, "daily", []) or []
    if not daily:
        return ""

    cards = []
    for item in daily:
        date = item.get("date") or "-"
        weather_text = f"{item.get('text_day') or '-'} / {item.get('text_night') or '-'}"
        temp = f"{item.get('low') or '-'}~{item.get('high') or '-'}°C"
        cards.append(
            f"""
<article class="row">
  <h3>{escape(date)}</h3>
  <span class="tag primary">{escape(weather_text)}</span>
  <span class="tag green">{escape(temp)}</span>
</article>
"""
        )
    update = getattr(weather, "last_update", None)
    return f"""
<section class="section">
  <h2>天气预报</h2>
  <div class="grid">{''.join(cards)}</div>
  {f'<p class="meta">更新时间：{escape(update)}</p>' if update else ''}
</section>
"""


def _render_transportation(state: dict[str, Any]) -> str:
    result = state.get("transportation_result")
    if result is None:
        return ""
    if not getattr(result, "recommended_plan", None):
        return _section_empty("交通方案", "当前没有可用的推荐交通方案。")

    plans = [result.recommended_plan, *getattr(result, "alternative_plans", [])]
    cards = []
    for plan in plans:
        mode = _transport_mode_label(plan.outbound.mode)
        cards.append(
            f"""
<article class="row">
  <h3>{escape(mode)}</h3>
  {_render_transport_option("去程", plan.outbound)}
  {_render_transport_option("返程", plan.return_trip) if plan.return_trip else ""}
  <div class="route">预计交通费用：{escape(str(plan.total_price or '待确认'))} 元/人</div>
  {_render_reminders(getattr(plan, "reminders", []))}
</article>
"""
        )

    return f"""
<section class="section">
  <h2>推荐交通方案</h2>
  <div class="two-col">{''.join(cards)}</div>
</section>
"""


def _render_hotels(state: dict[str, Any]) -> str:
    result = state.get("booking_result")
    if result is None:
        return ""
    hotels = getattr(result, "recommended_hotels", []) or []
    if not hotels:
        return _section_empty("酒店推荐", "暂无酒店推荐。")

    cards = []
    for hotel in hotels:
        distance = getattr(hotel, "distance_to_anchor_km", None)
        distance_text = f"<span class=\"tag green\">距首日景点约 {distance} km</span>" if distance is not None else ""
        booking = _button(getattr(hotel, "booking_url", None), "查看预订")
        cards.append(
            f"""
<article class="card">
  {_image(getattr(hotel, "image_url", None), getattr(hotel, "name", "酒店"))}
  <div class="card-body">
    <h3>{escape(getattr(hotel, 'name', '酒店'))}</h3>
    <span class="tag primary">{escape(getattr(hotel, 'price_display', None) or _format_price(getattr(hotel, 'price_per_night', None)))}</span>
    {distance_text}
    <p class="meta">{escape(getattr(hotel, 'distance_desc', None) or '')}</p>
    <p>{escape(getattr(hotel, 'address', None) or '')}</p>
    {booking}
  </div>
</article>
"""
        )

    return f"""
<section class="section">
  <h2>酒店推荐</h2>
  <div class="grid">{''.join(cards)}</div>
</section>
"""


def _render_budget(state: dict[str, Any]) -> str:
    result = state.get("budget_result")
    if result is None:
        return ""
    composition = _format_budget_composition(state)
    suggestions = "".join(f"<li>{escape(item)}</li>" for item in getattr(result, "suggestions", []) or [])
    return f"""
<section class="section">
  <h2>预算分析</h2>
  <div class="list">
    <div class="row"><strong>已计入核心费用</strong><div class="meta">{escape(str(result.total_cost))} 元</div></div>
    <div class="row"><strong>预算组成</strong><div class="meta">{escape(composition)}</div></div>
    <div class="row"><strong>剩余预算</strong><div class="meta">{escape(str(result.remaining_budget))} 元</div></div>
  </div>
  <ul>{suggestions}</ul>
</section>
"""


def _render_itinerary(state: dict[str, Any]) -> str:
    result = state.get("itinerary_result")
    if result is None:
        return ""
    day_cards = []
    for day in getattr(result, "days", []) or []:
        morning = _items(getattr(day, "morning", []))
        afternoon = _items(getattr(day, "afternoon", []))
        transfers = _items(getattr(day, "transfer_notes", []))
        day_cards.append(
            f"""
<article class="day">
  <h3>{escape(str(getattr(day, 'date', '') or ''))} {escape(getattr(day, 'theme', None) or '')}</h3>
  {f'<div class="time-block"><strong>天气</strong><ul><li>{escape(day.weather)}</li></ul></div>' if getattr(day, "weather", None) else ''}
  <div class="time-block"><strong>上午</strong>{morning}</div>
  {f'<div class="time-block"><strong>下午</strong>{afternoon}</div>' if getattr(day, "afternoon", []) else ''}
  {f'<div class="time-block"><strong>交通参考</strong>{transfers}</div>' if getattr(day, "transfer_notes", []) else ''}
</article>
"""
        )
    return f"""
<section class="section">
  <h2>最终行程</h2>
  <p class="meta">{escape(getattr(result, 'summary', '') or '')}</p>
  <div class="timeline">{''.join(day_cards)}</div>
</section>
"""


def _render_transport_option(label: str, option: Any) -> str:
    route = _transport_route(option)
    ref = getattr(option, "raw_reference", None) or "班次待确认"
    price = getattr(option, "price", None)
    price_text = f"{price} 元" if price is not None else "价格待确认"
    departure = _format_datetime(getattr(option, "departure_time", None)) or "时间待确认"
    arrival = _format_datetime(getattr(option, "arrival_time", None)) or "时间待确认"
    booking = _button(getattr(option, "booking_url", None), "订票链接")
    return f"""
<div class="route">
  <strong>{escape(label)}</strong>：{escape(route)} / {escape(ref)} / {escape(price_text)}<br />
  出发：{escape(departure)} ｜ 到达：{escape(arrival)}
  {booking}
</div>
"""


def _transport_route(option: Any) -> str:
    if getattr(option, "mode", None) == "flight":
        return (
            f"{_format_station(getattr(option, 'departure_station', None), getattr(option, 'departure_terminal', None))}"
            f" → {_format_station(getattr(option, 'arrival_station', None), getattr(option, 'arrival_terminal', None))}"
        )
    return f"{getattr(option, 'departure_city', '')} → {getattr(option, 'arrival_city', '')}"


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
        else "交通方案待确认"
    )
    hotel = (
        booking_result.recommended_hotels[0]
        if booking_result is not None and booking_result.recommended_hotels
        else None
    )
    hotel_label = hotel.name if hotel is not None else "酒店待确认"

    return (
        f"交通（{transport_label}）约 {breakdown.get('transport', 0)} 元 + "
        f"酒店（{hotel_label}）约 {breakdown.get('hotel', 0)} 元 + "
        f"已知景点门票约 {breakdown.get('tickets', 0)} 元"
    )


def _render_reminders(reminders: list[str]) -> str:
    if not reminders:
        return ""
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in reminders) + "</ul>"


def _items(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{escape(str(item))}</li>" for item in items) + "</ul>"


def _image(url: str | None, alt: str) -> str:
    if not url:
        return '<div class="cover"></div>'
    return f'<img class="cover" src="{escape(url)}" alt="{escape(alt)}" loading="lazy" />'


def _button(url: str | None, label: str) -> str:
    if not url:
        return ""
    return f'<br /><a class="button" href="{escape(url)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>'


def _section_empty(title: str, message: str) -> str:
    return f"""
<section class="section">
  <h2>{escape(title)}</h2>
  <div class="empty">{escape(message)}</div>
</section>
"""


def _format_admission(item: Any) -> str:
    status = getattr(item, "admission_status", None)
    ticket_price = getattr(item, "ticket_price", None)
    if status == "free":
        return "免费"
    if status == "known_paid" and ticket_price is not None:
        return f"约 {ticket_price} 元"
    if status == "unknown_paid":
        return "收费，价格待确认"
    return "待确认"


def _transport_mode_label(mode: str) -> str:
    return {"train": "高铁/动车", "flight": "飞机"}.get(mode, mode)


def _format_station(station: Any, terminal: Any) -> str:
    station_text = str(station) if station else "机场待确认"
    return f"{station_text}{terminal}" if terminal else station_text


def _format_price(value: Any) -> str:
    if value is None:
        return "价格待确认"
    if isinstance(value, (int, float)) and float(value).is_integer():
        return f"{int(value)} 元/晚"
    return f"{value} 元/晚"


def _format_datetime(value: Any) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M") if hasattr(value, "strftime") else str(value)
