from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Optional


# Amounts established from the supplied receipt/transaction images.
#
# None means the image did not provide sufficiently reliable evidence.
IMAGE_EVENT_AMOUNTS: dict[str, tuple[Optional[str], Optional[str]]] = {
    "event_253": ("4365000", "IDR"),
    "event_1442": ("63952", "INR"),
    "event_1545": ("41272", "INR"),
    "event_1700": (None, None),
    "event_1786": ("704.05", "INR"),
    "event_3051": ("1995", "INR"),
    "event_3231": ("8528.10", "INR"),
    "event_4535": ("15339", "INR"),
    "event_5170": ("723", "INR"),
    "event_6033": ("79679.26", "INR"),
    "event_6859": ("3650", "INR"),
    "event_7307": ("33.50", "USD"),
    "event_7941": ("2298", "INR"),
    "event_9421": ("3650", "INR"),
    "event_9806": ("9968", "INR"),
    "event_10521": ("393.22", "INR"),
}


def get_image_amount(
    event_id: str,
) -> tuple[Optional[Decimal], Optional[str]]:
    value = IMAGE_EVENT_AMOUNTS.get(event_id)

    if value is None:
        return None, None

    amount, currency = value

    if amount is None:
        return None, None

    return Decimal(amount), currency


def resolve_event_amounts(events):
    """
    Return a new event dictionary with reliably established missing
    amounts filled from image evidence.

    Existing CSV amounts are never overwritten.

    Unresolved amounts remain None.
    """

    resolved_events = {}

    for event_id, event in events.items():

        # Never overwrite a value already supplied by the dataset.
        if event.amount is not None:
            resolved_events[event_id] = event
            continue

        amount, currency = get_image_amount(event_id)

        if amount is None:
            resolved_events[event_id] = event
            continue

        # The event's currency is part of the original financial event.
        # We deliberately do not silently convert currencies here.
        #
        # Currency conversion belongs in the forecasting layer where
        # exchange_rates.csv is available.
        if currency != event.currency:
            raise ValueError(
                f"Evidence currency mismatch for {event_id}: "
                f"event={event.currency!r}, evidence={currency!r}"
            )

        resolved_events[event_id] = replace(
            event,
            amount=amount,
        )

    return resolved_events