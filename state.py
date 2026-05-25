from __future__ import annotations

import operator
from datetime import date as Date, datetime
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field


class Location(BaseModel):
    longitude: float | None = None
    latitude: float | None = None


class TravelRequirement(BaseModel):
    origin_city: str | None = None
    destination_city: str | None = None
    start_date: Date | None = None
    end_date: Date | None = None
    days: int | None = Field(default=None, ge=1)
    travelers: int = Field(default=1, ge=1)
    budget: float | None = Field(default=None, ge=0)
    preferences: list[str] = Field(default_factory=list)
    transport_preference: str | None = None
    hotel_preference: str | None = None
    special_constraints: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    clarification_needed: bool = False
    normalized_query: str | None = None


class RoutingInfo(BaseModel):
    days_until_departure: int | None = None
    weather_available: bool = False
    train_query_available: bool = False
    flight_query_available: bool = False
    hotel_query_available: bool = False
    transport_mode_strategy: Literal[
        "train_first", "flight_first", "mixed", "reference_only"
    ] = "reference_only"
    degraded_mode: bool = False
    degradation_reasons: list[str] = Field(default_factory=list)
    data_freshness_note: str | None = None


class WeatherInfo(BaseModel):
    city: str
    summary: str | None = None
    temperature_c: float | None = None
    forecast: list[str] = Field(default_factory=list)
    daily: list[dict[str, str | None]] = Field(default_factory=list)
    last_update: str | None = None
    is_available: bool = True
    unavailable_reason: str | None = None


class Attraction(BaseModel):
    name: str
    address: str | None = None
    location: Location | None = None
    category: str | None = None
    admission_status: Literal["free", "known_paid", "unknown_paid", "unknown"] = (
        "unknown"
    )
    rating: float | None = None
    ticket_price: float | None = None
    visit_duration: int | None = None
    description: str | None = None
    image_url: str | None = None


class AttractionRecommendation(BaseModel):
    name: str
    reason: str
    description: str | None = None
    full_description: str | None = None
    image_url: str | None = None
    address: str | None = None
    admission_status: Literal["free", "known_paid", "unknown_paid", "unknown"] | None = None
    ticket_price: float | None = None


class Restaurant(BaseModel):
    name: str
    address: str | None = None
    location: Location | None = None
    category: str | None = None
    average_cost: float | None = None
    rating: float | None = None
    description: str | None = None


class AttractionResult(BaseModel):
    attractions: list[Attraction] = Field(default_factory=list)
    restaurants: list[Restaurant] = Field(default_factory=list)
    weather: WeatherInfo | None = None
    recommended_attractions: list[AttractionRecommendation] = Field(
        default_factory=list
    )
    notes: list[str] = Field(default_factory=list)
    source_summary: list[str] = Field(default_factory=list)
    is_fallback: bool = False


class TransportOption(BaseModel):
    mode: Literal["train", "flight", "reference"]
    provider: str
    departure_city: str
    arrival_city: str
    departure_station: str | None = None
    arrival_station: str | None = None
    departure_terminal: str | None = None
    arrival_terminal: str | None = None
    departure_time: datetime | None = None
    arrival_time: datetime | None = None
    duration_minutes: int | None = None
    price: float | None = None
    seat_or_class: str | None = None
    raw_reference: str | None = None
    transfer_cities: list[str] = Field(default_factory=list)
    transfer_duration_minutes: int | None = None
    booking_url: str | None = None


class TransportPlan(BaseModel):
    outbound: TransportOption
    return_trip: TransportOption | None = None
    total_price: float | None = None
    total_duration_minutes: int | None = None
    score: float | None = None
    reason: str | None = None
    reminders: list[str] = Field(default_factory=list)


class TransportationResult(BaseModel):
    outbound_options: list[TransportOption] = Field(default_factory=list)
    return_options: list[TransportOption] = Field(default_factory=list)
    recommended_plan: TransportPlan | None = None
    alternative_plans: list[TransportPlan] = Field(default_factory=list)
    selection_reason: str | None = None
    source_summary: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    is_fallback: bool = False


class Hotel(BaseModel):
    name: str
    address: str | None = None
    location: Location | None = None
    price_per_night: float | None = None
    price_display: str | None = None
    price_is_starting: bool = False
    rating: float | None = None
    distance_desc: str | None = None
    distance_to_anchor_km: float | None = None
    hotel_type: str | None = None
    image_url: str | None = None
    booking_url: str | None = None


class BookingResult(BaseModel):
    hotels: list[Hotel] = Field(default_factory=list)
    recommended_hotels: list[Hotel] = Field(default_factory=list)
    search_strategy: list[str] = Field(default_factory=list)
    selection_reason: str | None = None
    source_summary: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    is_fallback: bool = False


class BudgetResult(BaseModel):
    transport_cost: float = 0
    hotel_cost: float = 0
    ticket_cost: float = 0
    meal_cost: float = 0
    misc_cost: float = 0
    total_cost: float = 0
    remaining_budget: float | None = None
    is_over_budget: bool | None = None
    cost_breakdown: dict[str, float] = Field(default_factory=dict)
    suggestions: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"


class DayPlan(BaseModel):
    date: Date | None = None
    theme: str | None = None
    weather: str | None = None
    morning: list[str] = Field(default_factory=list)
    lunch: list[str] = Field(default_factory=list)
    afternoon: list[str] = Field(default_factory=list)
    dinner: list[str] = Field(default_factory=list)
    evening: list[str] = Field(default_factory=list)
    transfer_notes: list[str] = Field(default_factory=list)
    hotel: str | None = None
    estimated_daily_cost: float | None = None


class ItineraryResult(BaseModel):
    days: list[DayPlan] = Field(default_factory=list)
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)
    travel_tips: list[str] = Field(default_factory=list)
    budget_note: str | None = None
    transport_note: str | None = None
    warnings: list[str] = Field(default_factory=list)


class AgentError(BaseModel):
    agent_name: str
    error_type: str
    message: str
    recoverable: bool = True
    fallback_used: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)


class TravelPlanState(TypedDict, total=False):
    raw_user_input: str
    requirement: TravelRequirement
    routing_info: RoutingInfo
    attraction_result: AttractionResult
    transportation_result: TransportationResult
    booking_result: BookingResult
    budget_result: BudgetResult
    itinerary_result: ItineraryResult
    errors: Annotated[list[AgentError], operator.add]
    warnings: Annotated[list[str], operator.add]
    current_phase: str | None
    status: Literal["pending", "running", "partial", "completed", "failed"]
