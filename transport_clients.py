from __future__ import annotations

from datetime import date

from flyai_client import FlyAIClient
from mcp_12306_client import MCP12306Client
from state import Hotel, TransportOption


class TransportClients:
    """Integration seam for 12306 and FlyAI.

    Centralized transport / booking integrations.
    """

    def __init__(self) -> None:
        self.mcp_12306 = MCP12306Client()
        self.flyai = FlyAIClient()

    def query_12306_trains(
        self, origin_city: str, destination_city: str, travel_date: date
    ) -> list[TransportOption]:
        return self.mcp_12306.query_tickets(
            origin_city=origin_city,
            destination_city=destination_city,
            travel_date=travel_date,
        )

    def query_flyai_flights(
        self, origin_city: str, destination_city: str, travel_date: date
    ) -> list[TransportOption]:
        return self.flyai.search_flights(
            origin_city=origin_city,
            destination_city=destination_city,
            travel_date=travel_date,
        )

    def query_flyai_hotels(
        self,
        destination_city: str,
        check_in: date,
        check_out: date,
        hotel_preference: str | None = None,
        poi_name: str | None = None,
    ) -> list[Hotel]:
        return self.flyai.search_hotels(
            destination_city=destination_city,
            check_in=check_in,
            check_out=check_out,
            hotel_preference=hotel_preference,
            poi_name=poi_name,
        )
