from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EventDirection(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"
    NON_CASH = "non_cash"

class EventStatus(str, Enum):
    SETTLED = "settled"
    PENDING = "pending"
    SCHEDULED = "scheduled"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNREALIZED = "unrealized"


class EvidenceSourceType(str, Enum):
    MESSAGE = "message"
    IMAGE = "image"


class EvidenceFactType(str, Enum):
    AMOUNT = "amount"
    DATE = "date"
    STATUS = "status"
    DESCRIPTION = "description"
    INCOME = "income"
    EXPENSE = "expense"
    PAYMENT = "payment"
    REFUND = "refund"
    CANCELLATION = "cancellation"
    AMENDMENT = "amendment"
    OTHER = "other"


class PaymentMethod(str, Enum):
    FULL_PAYMENT = "full_payment"
    PARTIAL_PAYMENT = "partial_payment"
    INSTALLMENTS = "installments"
    WAIT = "wait"
    NOT_RECOMMENDED = "not_recommended"


# ---------------------------------------------------------------------------
# Core financial records
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FinancialProfile:
    user_id: str
    home_currency: str

    current_available_balance: Decimal
    minimum_balance_to_keep: Decimal

    financial_priorities: tuple[str, ...]
    protected_categories: tuple[str, ...]
    reducible_categories: tuple[str, ...]
    stoppable_categories: tuple[str, ...]

    payment_methods_user_will_consider: tuple[str, ...]
    max_installment_months: Optional[int]


@dataclass(frozen=True)
class FinancialEvent:
    event_id: str
    user_id: str

    event_type: str
    description: str
    category: str

    direction: EventDirection
    amount: Optional[Decimal]
    currency: str

    event_date: date
    settlement_date: Optional[date]

    status: EventStatus
    linked_event_id: Optional[str]

    flexibility: Optional[str]
    minimum_allowed_amount: Optional[Decimal]


@dataclass(frozen=True)
class FinancialRequest:
    request_id: str
    user_id: str

    request_date: date
    request_type: str

    requested_amount: Decimal
    desired_completion_date: date

    allows_partial_payment: bool
    request_text: str


@dataclass(frozen=True)
class PaymentOption:
    payment_option_id: str
    request_id: str

    payment_method: str
    payment_amount: Decimal

    number_of_payments: int
    first_payment_date: date
    payment_frequency_days: Optional[int]

    financing_fee: Decimal
    total_payable_amount: Decimal

@dataclass(frozen=True)
class ExchangeRate:
    rate_date: date
    from_currency: str
    to_currency: str
    rate: Decimal

# ---------------------------------------------------------------------------
# Supporting evidence
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MessageRecord:
    message_id: str
    user_id: str

    request_id: Optional[str]
    related_event_id: Optional[str]

    sent_at: datetime
    source_type: str
    message_text: str


@dataclass(frozen=True)
class ImageRecord:
    image_id: str
    user_id: str

    request_id: Optional[str]
    related_event_id: Optional[str]

    file_path: Path


# ---------------------------------------------------------------------------
# LLM / VLM extraction
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceFact:
    """
    A claim extracted from an untrusted message or image.

    This is NOT a financial decision and does NOT directly modify
    FinancialEvent or FinancialProfile.
    """

    source_type: EvidenceSourceType
    source_id: str

    user_id: str
    request_id: Optional[str]
    related_event_id: Optional[str]

    fact_type: EvidenceFactType

    # Normalized value extracted from the source.
    value: str

    # Original text supporting the extraction, when available.
    evidence_text: Optional[str]

    # Model confidence. This is never sufficient by itself to authorize
    # a financial state change.
    confidence: Optional[float]


@dataclass(frozen=True)
class EvidenceExtraction:
    """
    Complete result from processing one message/image.
    """

    source_type: EvidenceSourceType
    source_id: str

    facts: tuple[EvidenceFact, ...]

    # True when the model detected content that looks like an instruction
    # aimed at the AI rather than financial evidence.
    prompt_injection_detected: bool

    # Human-readable reason for rejecting/limiting the extraction.
    warnings: tuple[str, ...]


# ---------------------------------------------------------------------------
# Derived financial state
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CashFlow:
    date: date
    amount: Decimal
    currency: str
    event_id: Optional[str]
    description: str


@dataclass(frozen=True)
class BalanceSnapshot:
    date: date
    balance: Decimal
    minimum_required: Decimal

    @property
    def is_safe(self) -> bool:
        return self.balance >= self.minimum_required


@dataclass(frozen=True)
class PaymentPlanEntry:
    payment_date: date
    amount: Decimal


@dataclass(frozen=True)
class CandidatePlan:
    payment_method: PaymentMethod
    payments: tuple[PaymentPlanEntry, ...]

    spending_changes: tuple[str, ...]

    total_amount_paid: Decimal
    completes_by_deadline: bool


# ---------------------------------------------------------------------------
# Final decision
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FinancialDecision:
    request_id: str

    amount_safe_to_pay: Decimal

    affordability_status: str
    recommended_payment_method: PaymentMethod

    payment_plan: tuple[PaymentPlanEntry, ...]

    earliest_date_for_full_payment: Optional[date]

    spending_changes_needed: tuple[str, ...]

    decision_explanation: str