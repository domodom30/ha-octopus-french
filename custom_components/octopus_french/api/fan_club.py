"""API client for the Octopus Fan Club offer."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from octopus_french.octopus_french import OctopusFrenchApiClient

_LOGGER = logging.getLogger(__name__)

QUERY_FAN_CLUB_STATUS = """
query fanClubStatus($accountNumber: String!) {
  fanClubStatus(accountNumber: $accountNumber) {
    discountSource
    current {
      startAt
      discount
    }
    historic {
      startAt
      discount
    }
    forecast {
      baseTime
      data {
        validTime
        projectedDiscount
      }
    }
  }
}
"""


class OctopusFanClubApiClient:
    """Client for the Fan Club wind farm discount."""

    def __init__(self, api_client: OctopusFrenchApiClient) -> None:
        """Initialize the Fan Club client."""
        self.api_client = api_client

    async def get_fan_club_status(self, account_number: str) -> list[dict[str, Any]]:
        """Return the Fan Club statuses of an account, empty when not subscribed."""
        response = await self.api_client.execute_with_auth(
            QUERY_FAN_CLUB_STATUS, {"accountNumber": account_number}
        )
        statuses = (
            (response.get("data") or {}).get("fanClubStatus") if response else None
        )
        _LOGGER.debug("Fan Club status for account %s: %s", account_number, statuses)
        if not isinstance(statuses, list):
            return []
        return [
            status
            for status in statuses
            if isinstance(status, dict) and status.get("discountSource")
        ]
