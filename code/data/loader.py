from __future__ import annotations

from agents.evidence_amounts import resolve_event_amounts

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .models import (
    EvidenceSourceType,
    FinancialEvent,
    FinancialProfile,
    FinancialRequest,
    EventDirection,
    EventStatus,
    ImageRecord,
    MessageRecord,
    PaymentOption,
    ExchangeRate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(value: Optional[str]) -> str:
    if value is None:
        return ""
    return value.strip()


def _optional(value: Optional[str]) -> Optional[str]:
    value = _clean(value)
    return value if value else None


def _decimal(value: Optional[str]) -> Optional[Decimal]:
    value = _clean(value)

    if not value:
        return None

    return Decimal(value)


def _required_decimal(value: Optional[str]) -> Decimal:
    parsed = _decimal(value)

    if parsed is None:
        raise ValueError("Required decimal value is missing")

    return parsed


def _date(value: str) -> date:
    return date.fromisoformat(_clean(value))


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(_clean(value).replace("Z", "+00:00"))


def _split_pipe(value: Optional[str]) -> tuple[str, ...]:
    value = _clean(value)

    if not value:
        return ()

    return tuple(
        item.strip()
        for item in value.split("|")
        if item.strip()
    )


def _bool(value: str) -> bool:
    value = _clean(value).lower()

    if value in {"true", "1", "yes"}:
        return True

    if value in {"false", "0", "no"}:
        return False

    raise ValueError(f"Cannot parse boolean value: {value!r}")


# ---------------------------------------------------------------------------
# CSV reader
# ---------------------------------------------------------------------------

def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset file not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError(f"CSV has no header: {path}")

        return list(reader)


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def load_profiles(dataset_dir: Path) -> dict[str, FinancialProfile]:
    rows = _read_csv(dataset_dir / "financial_profiles.csv")

    profiles: dict[str, FinancialProfile] = {}

    for row in rows:
        user_id = _clean(row["user_id"])

        if not user_id:
            continue

        profiles[user_id] = FinancialProfile(
            user_id=user_id,
            home_currency=_clean(row["home_currency"]),
            current_available_balance=_required_decimal(
                row["current_available_balance"]
            ),
            minimum_balance_to_keep=_required_decimal(
                row["minimum_balance_to_keep"]
            ),
            financial_priorities=_split_pipe(
                row["financial_priorities"]
            ),
            protected_categories=_split_pipe(
                row["expense_categories_to_protect"]
            ),
            reducible_categories=_split_pipe(
                row["expense_categories_user_is_willing_to_reduce"]
            ),
            stoppable_categories=_split_pipe(
                row["expense_categories_user_is_willing_to_stop"]
            ),
            payment_methods_user_will_consider=_split_pipe(
                row["payment_methods_user_will_consider"]
            ),
            max_installment_months=(
                int(float(row["max_installment_months"]))
                if _clean(row["max_installment_months"])
                else None
            ),
        )

    return profiles


# ---------------------------------------------------------------------------
# Financial events
# ---------------------------------------------------------------------------

def load_events(dataset_dir: Path) -> dict[str, FinancialEvent]:
    rows = _read_csv(dataset_dir / "financial_events.csv")

    events: dict[str, FinancialEvent] = {}

    for row in rows:
        event_id = _clean(row["event_id"])

        if not event_id:
            continue

        events[event_id] = FinancialEvent(
            event_id=event_id,
            user_id=_clean(row["user_id"]),
            event_type=_clean(row["event_type"]),
            description=_clean(row["description"]),
            category=_clean(row["category"]),
            direction=EventDirection(_clean(row["direction"])),
            amount=_decimal(row["amount"]),
            currency=_clean(row["currency"]),
            event_date=_date(row["event_date"]),
            settlement_date=(
                _date(row["settlement_date"])
                if _clean(row["settlement_date"])
                else None
            ),
            status=EventStatus(_clean(row["status"])),
            linked_event_id=_optional(row["linked_event_id"]),
            flexibility=_optional(row["flexibility"]),
            minimum_allowed_amount=_decimal(
                row["minimum_allowed_amount"]
            ),
        )

    return events


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

def load_requests(dataset_dir: Path) -> dict[str, FinancialRequest]:
    rows = _read_csv(dataset_dir / "requests.csv")

    requests: dict[str, FinancialRequest] = {}

    for row in rows:
        request_id = _clean(row["request_id"])

        if not request_id:
            continue

        requests[request_id] = FinancialRequest(
            request_id=request_id,
            user_id=_clean(row["user_id"]),
            request_date=_date(row["request_date"]),
            request_type=_clean(row["request_type"]),
            requested_amount=_required_decimal(
                row["requested_amount"]
            ),
            desired_completion_date=_date(
                row["desired_completion_date"]
            ),
            allows_partial_payment=_bool(
                row["allows_partial_payment"]
            ),
            request_text=_clean(row["request_text"]),
        )

    return requests


# ---------------------------------------------------------------------------
# Payment options
# ---------------------------------------------------------------------------

def load_payment_options(
    dataset_dir: Path,
) -> dict[str, list[PaymentOption]]:
    rows = _read_csv(dataset_dir / "request_payment_options.csv")

    options: dict[str, list[PaymentOption]] = {}

    for row in rows:
        request_id = _clean(row["request_id"])

        if not request_id:
            continue

        option = PaymentOption(
            payment_option_id=_clean(row["payment_option_id"]),
            request_id=request_id,
            payment_method=_clean(row["payment_method"]),
            payment_amount=_required_decimal(
                row["payment_amount"]
            ),
            number_of_payments=int(
                float(row["number_of_payments"])
            ),
            first_payment_date=_date(
                row["first_payment_date"]
            ),
            payment_frequency_days=(
                int(float(row["payment_frequency_days"]))
                if _clean(row["payment_frequency_days"])
                else None
            ),
            financing_fee=_required_decimal(
                row["financing_fee"]
            ),
            total_payable_amount=_required_decimal(
                row["total_payable_amount"]
            ),
        )

        options.setdefault(request_id, []).append(option)

    return options


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def load_messages(
    dataset_dir: Path,
) -> dict[str, list[MessageRecord]]:
    rows = _read_csv(dataset_dir / "messages.csv")

    messages: dict[str, list[MessageRecord]] = {}

    for row in rows:
        user_id = _clean(row["user_id"])

        if not user_id:
            continue

        message = MessageRecord(
            message_id=_clean(row["message_id"]),
            user_id=user_id,
            request_id=_optional(row["request_id"]),
            related_event_id=_optional(row["related_event_id"]),
            sent_at=_datetime(row["sent_at"]),
            source_type=_clean(row["source_type"]),
            message_text=_clean(row["message_text"]),
        )

        messages.setdefault(user_id, []).append(message)

    return messages


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def load_images(
    dataset_dir: Path,
) -> dict[str, ImageRecord]:
    rows = _read_csv(dataset_dir / "images.csv")

    image_dir = dataset_dir / "media" / "images"

    images: dict[str, ImageRecord] = {}

    for row in rows:
        image_id = _clean(row["image_id"])

        if not image_id:
            continue

        file_path = image_dir / f"{image_id}.png"

        images[image_id] = ImageRecord(
            image_id=image_id,
            user_id=_clean(row["user_id"]),
            request_id=_optional(row["request_id"]),
            related_event_id=_optional(row["related_event_id"]),
            file_path=file_path,
        )

    return images

# ---------------------------------------------------------------------------
# Exchange rates
# ---------------------------------------------------------------------------

def load_exchange_rates(
    dataset_dir: Path,
) -> list[ExchangeRate]:

    rows = _read_csv(dataset_dir / "exchange_rates.csv")

    rates: list[ExchangeRate] = []

    for row in rows:
        rates.append(
            ExchangeRate(
                rate_date=_date(row["rate_date"]),
                from_currency=_clean(row["from_currency"]),
                to_currency=_clean(row["to_currency"]),
                rate=_required_decimal(row["rate"]),
            )
        )

    return rates
# ---------------------------------------------------------------------------
# Complete dataset
# ---------------------------------------------------------------------------

@dataclass
class Dataset:
    profiles: dict[str, FinancialProfile]
    events: dict[str, FinancialEvent]
    requests: dict[str, FinancialRequest]

    payment_options: dict[str, list[PaymentOption]]

    messages: dict[str, list[MessageRecord]]
    images: dict[str, ImageRecord]
    exchange_rates: list[ExchangeRate]


def load_dataset(dataset_dir: str | Path) -> Dataset:
    dataset_dir = Path(dataset_dir)

    profiles = load_profiles(dataset_dir)
    events = load_events(dataset_dir)
    requests = load_requests(dataset_dir)
    payment_options = load_payment_options(dataset_dir)
    messages = load_messages(dataset_dir)
    images = load_images(dataset_dir)
    exchange_rates = load_exchange_rates(dataset_dir)

    events = resolve_event_amounts(events)

    return Dataset(
        profiles=profiles,
        events=events,
        requests=requests,
        payment_options=payment_options,
        messages=messages,
        images=images,
        exchange_rates=exchange_rates,
    )