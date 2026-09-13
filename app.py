from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import gradio as gr
import pandas as pd
from dotenv import load_dotenv
from google import genai


# ============================================================
# CONFIG
# ============================================================

ROOT = Path(__file__).resolve().parent
OUTPUT_CSV = ROOT / "dataset" / "output.csv"

load_dotenv(dotenv_path=ROOT / ".env")

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite",
)


# ============================================================
# GEMINI
# ============================================================

def gemini_understand(text: str) -> dict:
    """
    Gemini is used only for request understanding/enrichment.

    Financial affordability is NOT delegated to Gemini.
    """

    if not GEMINI_KEY:
        return {
            "available": False,
            "reason": "Gemini API key not configured.",
            "description": None,
            "request_type": None,
            "date": None,
        }

    prompt = f"""
Extract useful non-financial-semantic information from this financial
request.

Do NOT calculate affordability.
Do NOT decide whether the purchase is safe.
Do NOT invent balances, fees, dates, or payment terms.

Return ONLY valid JSON:

{{
  "description": "item/service being purchased",
  "request_type": "purchase|travel|education|housing|emergency_expense|other",
  "completion_date": "YYYY-MM-DD or null"
}}

User request:
{text}
"""

    try:
        client = genai.Client(api_key=GEMINI_KEY)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )

        raw = (response.text or "").strip()

        # Remove markdown fences if Gemini adds them.
        raw = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            raw,
            flags=re.IGNORECASE,
        ).strip()

        data = json.loads(raw)

        return {
            "available": True,
            "reason": None,
            "description": data.get("description"),
            "request_type": data.get("request_type"),
            "date": data.get("completion_date"),
        }

    except Exception as exc:
        return {
            "available": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "description": None,
            "request_type": None,
            "date": None,
        }


# ============================================================
# LOCAL DETERMINISTIC UNDERSTANDING
# ============================================================

CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "₹": "INR",
}


def parse_decimal(value) -> Decimal | None:
    if value is None:
        return None

    if isinstance(value, Decimal):
        return value

    raw = str(value).strip()

    if not raw:
        return None

    raw = re.sub(r"[^0-9.\-]", "", raw.replace(",", ""))

    if not raw:
        return None

    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def money_regex():
    return (
        r"(?P<currency>\$|€|£|₹|[A-Za-z]{3})"
        r"\s*"
        r"(?P<amount>\d+(?:,\d{3})*(?:\.\d+)?)"
    )


def read_money(match):
    if not match:
        return None, None

    raw_currency = match.group("currency")
    raw_amount = match.group("amount").replace(",", "")

    currency = CURRENCY_SYMBOLS.get(
        raw_currency,
        raw_currency.upper(),
    )

    try:
        amount = Decimal(raw_amount)
    except InvalidOperation:
        return None, currency

    return amount, currency


def extract_money_roles(text: str) -> dict:
    """
    Deterministic semantic role extraction.

    Important:
    We do NOT use largest/smallest amount heuristics.
    """

    result = {
        "balance": None,
        "minimum_balance": None,
        "requested_amount": None,
        "currency": None,
        "income": None,
        "expense": None,
        "financing_fee": None,
    }

    money = money_regex()

    # --------------------------------------------------------
    # BALANCE
    # --------------------------------------------------------

    balance_patterns = [
        rf"\b(?:i\s+have|i['’]ve\s+got)\s+{money}\s+(?:in|on)\s+(?:my|the)\s+(?:account|bank|savings)",
        rf"\b(?:my|current|available)\s+balance\s+is\s+{money}",
        rf"\b(?:i\s+have|i['’]ve\s+got)\s+{money}\b",
    ]

    for pattern in balance_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount, currency = read_money(match)

            if amount is not None:
                result["balance"] = amount
                result["currency"] = currency
                break

    # --------------------------------------------------------
    # MINIMUM PROTECTED
    # --------------------------------------------------------

    minimum_patterns = [
        rf"\bkeep\s+{money}\b",
        rf"\bleave\s+{money}\b",
        rf"\breserve\s+{money}\b",
        rf"\bretain\s+{money}\b",
        rf"\bprotect\s+{money}\b",
        rf"\bat\s+least\s+{money}\b",
        rf"{money}\s+(?:untouched|protected|reserved)\b",
    ]

    for pattern in minimum_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount, currency = read_money(match)

            if amount is not None:
                result["minimum_balance"] = amount
                result["currency"] = result["currency"] or currency
                break

    # --------------------------------------------------------
    # REQUEST AMOUNT
    # --------------------------------------------------------

    request_patterns = [
        rf"\bconsidering\s+(?:a|an)?\s*{money}\b",
        rf"\blooking\s+at\s+(?:a|an)?\s*{money}\b",
        rf"\blooking\s+to\s+buy\s+(?:a|an)?\s*{money}\b",
        rf"\bbuy\s+(?:a|an)?\s*{money}\b",
        rf"\bpurchase\s+(?:a|an)?\s*{money}\b",
        rf"\b(?:price|cost)\s+(?:is|of)\s*{money}\b",
    ]

    for pattern in request_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount, currency = read_money(match)

            if amount is not None:
                result["requested_amount"] = amount
                result["currency"] = result["currency"] or currency
                break

    # "laptop costs ZAR 33,114"
    if result["requested_amount"] is None:
        match = re.search(
            rf"\b(?:laptop|phone|computer|car|item)\s+"
            rf"(?:costs?|is\s+priced\s+at)\s*{money}\b",
            text,
            re.IGNORECASE,
        )

        if match:
            amount, currency = read_money(match)

            if amount is not None:
                result["requested_amount"] = amount
                result["currency"] = result["currency"] or currency

    # --------------------------------------------------------
    # OTHER FINANCIAL FLOWS
    # --------------------------------------------------------

    income_match = re.search(
        rf"\b(?:salary|income|bonus|paycheck)\s+"
        rf"(?:of|is)?\s*{money}\b",
        text,
        re.IGNORECASE,
    )

    if income_match:
        amount, _ = read_money(income_match)
        result["income"] = amount

    expense_match = re.search(
        rf"\b(?:rent|bill|expense|debt|payment)\s+"
        rf"(?:of|is|due)?\s*{money}\b",
        text,
        re.IGNORECASE,
    )

    if expense_match:
        amount, _ = read_money(expense_match)
        result["expense"] = amount

    fee_match = re.search(
        rf"\b(?:fee|interest|charge|financing\s+cost)\s+"
        rf"(?:of|is)?\s*{money}\b",
        text,
        re.IGNORECASE,
    )

    if fee_match:
        amount, _ = read_money(fee_match)
        result["financing_fee"] = amount

    # --------------------------------------------------------
    # FALLBACK WHEN THERE IS ONLY ONE MONEY VALUE
    # --------------------------------------------------------

    all_money = list(
        re.finditer(money, text, re.IGNORECASE)
    )

    if (
        result["requested_amount"] is None
        and len(all_money) == 1
    ):
        amount, currency = read_money(all_money[0])
        result["requested_amount"] = amount
        result["currency"] = result["currency"] or currency

    return result


def extract_payment_plan(text: str) -> dict:
    count = None
    frequency = None

    patterns = [
        r"\b(\d+)\s+monthly\s+installments?\b",
        r"\b(\d+)\s+monthly\s+payments?\b",
        r"\bpay\s+(?:it|this|that)\s+in\s+(\d+)\s+payments?\b",
        r"\b(\d+)\s+installments?\b",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            count = int(match.group(1))

            if re.search(
                r"monthly|month",
                match.group(0),
                re.IGNORECASE,
            ):
                frequency = "monthly"
            elif re.search(
                r"weekly|week",
                match.group(0),
                re.IGNORECASE,
            ):
                frequency = "weekly"

            break

    return {
        "count": count,
        "frequency": frequency,
    }


def detect_request_type(text: str) -> str:
    low = text.lower()

    if any(
        x in low
        for x in (
            "laptop",
            "phone",
            "computer",
            "car",
            "buy",
            "purchase",
        )
    ):
        return "purchase"

    if any(x in low for x in ("trip", "travel", "flight", "hotel")):
        return "travel"

    if any(x in low for x in ("course", "tuition", "education")):
        return "education"

    if any(x in low for x in ("rent", "house", "deposit")):
        return "housing"

    if any(x in low for x in ("repair", "emergency")):
        return "emergency_expense"

    return "other"


def parse_completion_date(text: str):
    match = re.search(
        r"\b(20\d{2}-\d{2}-\d{2})\b",
        text,
    )

    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            pass

    return None


# ============================================================
# DETERMINISTIC FINANCIAL DECISION
# ============================================================

def money(currency, value):
    if value is None:
        return "N/A"

    return f"{currency} {value:,.2f}"


def decide(
    balance: Decimal,
    minimum: Decimal,
    amount: Decimal,
    payment_count: int | None,
    frequency: str | None,
    future_income: Decimal | None = None,
    future_expense: Decimal | None = None,
    currency: str = "USD",
):
    """
    Deterministic financial decision.

    No LLM decision-making.
    """

    if balance < Decimal("0"):
        balance = Decimal("0")

    if minimum < Decimal("0"):
        minimum = Decimal("0")

    if amount <= Decimal("0"):
        return {
            "status": "not_affordable",
            "safe": Decimal("0"),
            "method": "not_recommended",
            "plan": "none",
            "earliest": None,
            "spending": "None",
            "explanation": "The requested amount must be greater than zero.",
        }

    usable_now = max(
        Decimal("0"),
        balance - minimum,
    )

    # Full payment.
    if amount <= usable_now:
        return {
            "status": "affordable_now",
            "safe": amount,
            "method": "full_payment",
            "plan": f"{date.today().isoformat()}:{amount:.2f}",
            "earliest": date.today(),
            "spending": "None",
            "explanation": (
                f"The full requested amount fits within the amount "
                f"available above the protected minimum balance."
            ),
        }

    # Explicit installment plan.
    if payment_count and payment_count > 1:
        installment = (
            amount / Decimal(payment_count)
        ).quantize(Decimal("0.01"))

        running_balance = balance
        plan_dates = []

        for index in range(payment_count):
            payment_date = date.today()

            if frequency == "monthly":
                # Deterministic 30-day approximation for the custom demo.
                payment_date = date.today() + timedelta(
                    days=30 * index
                )
            elif frequency == "weekly":
                payment_date = date.today() + timedelta(
                    days=7 * index
                )

            running_balance -= installment

            if running_balance < minimum:
                break

            plan_dates.append(
                f"{payment_date.isoformat()}:{installment:.2f}"
            )

        if len(plan_dates) == payment_count:
            return {
                "status": "affordable_with_plan",
                "safe": min(
                    usable_now,
                    amount,
                ),
                "method": "installments",
                "plan": "|".join(plan_dates),
                "earliest": None,
                "spending": "None",
                "explanation": (
                    f"The full request is affordable using the "
                    f"explicit {payment_count}-payment plan while "
                    f"maintaining the protected minimum."
                ),
            }

    # Future known cash flow.
    future_balance = balance

    if future_income:
        future_balance += future_income

    if future_expense:
        future_balance -= future_expense

    future_usable = max(
        Decimal("0"),
        future_balance - minimum,
    )

    if amount <= future_usable:
        future_date = date.today() + timedelta(days=30)

        return {
            "status": "affordable_later",
            "safe": usable_now,
            "method": "wait",
            "plan": "none",
            "earliest": future_date,
            "spending": "None",
            "explanation": (
                f"The full request is not safe today while keeping "
                f"the protected minimum, but the projected cash position "
                f"supports it later."
            ),
        }

    return {
        "status": "not_affordable",
        "safe": usable_now,
        "method": "not_recommended",
        "plan": "none",
        "earliest": None,
        "spending": "None",
        "explanation": (
            f"The requested amount cannot be paid safely while "
            f"maintaining the required minimum protected balance "
            f"across the current projection."
        ),
    }


# ============================================================
# CUSTOM AGENT
# ============================================================

def analyze_custom(
    request_text,
    balance_override,
    minimum_override,
    currency_override,
    date_override,
    income_override,
    expense_override,
):
    try:
        text = (request_text or "").strip()

        if not text:
            return render_missing(
                "Please describe your financial situation and purchase request."
            )

        # Gemini = understanding/enrichment.
        gemini = gemini_understand(text)

        # Deterministic role extraction owns financial values.
        roles = extract_money_roles(text)
        plan = extract_payment_plan(text)

        request_type = (
            gemini.get("request_type")
            or detect_request_type(text)
        )

        completion_date = (
            parse_completion_date(text)
            or (
                date.fromisoformat(date_override.strip())
                if date_override and date_override.strip()
                else None
            )
        )

        # Explicit overrides are allowed.
        if balance_override and str(balance_override).strip():
            roles["balance"] = parse_decimal(balance_override)

        if minimum_override and str(minimum_override).strip():
            roles["minimum_balance"] = parse_decimal(
                minimum_override
            )

        if currency_override and str(currency_override).strip():
            roles["currency"] = str(
                currency_override
            ).strip().upper()

        future_income = None
        future_expense = None

        if income_override and str(income_override).strip():
            future_income = parse_decimal(income_override)

        if expense_override and str(expense_override).strip():
            future_expense = parse_decimal(expense_override)

        missing = []

        if roles["requested_amount"] is None:
            missing.append("requested purchase amount")

        if roles["balance"] is None:
            missing.append("current account balance")

        if roles["minimum_balance"] is None:
            missing.append("minimum protected balance")

        if roles["currency"] is None:
            missing.append("currency")

        if missing:
            return render_missing(
                "I need: " + ", ".join(missing),
                roles,
                plan,
                gemini,
            )

        decision = decide(
            balance=roles["balance"],
            minimum=roles["minimum_balance"],
            amount=roles["requested_amount"],
            payment_count=plan["count"],
            frequency=plan["frequency"],
            future_income=future_income,
            future_expense=future_expense,
            currency=roles["currency"],
        )

        status = decision["status"]

        emoji = {
            "affordable_now": "🟢",
            "affordable_with_plan": "🟡",
            "affordable_later": "🟠",
            "not_affordable": "🔴",
        }.get(status, "🔴")

        gemini_state = (
            "Gemini used for request understanding"
            if gemini.get("available")
            else "Gemini unavailable → deterministic fallback"
        )

        earliest = (
            decision["earliest"].isoformat()
            if decision["earliest"]
            else "N/A"
        )

        description = (
            gemini.get("description")
            or request_type
        )

        guardrails = (
            "Gemini handles request understanding only.\n"
            "Financial amounts are resolved deterministically.\n"
            "The protected minimum balance is enforced.\n"
            "Installments are used only when explicitly stated.\n"
            "Financing fees are never invented.\n"
            "Missing financial information is requested instead of guessed."
        )

        agent_state = (
            f"**Requested amount:** "
            f"{money(roles['currency'], roles['requested_amount'])}\n\n"
            f"**Current balance:** "
            f"{money(roles['currency'], roles['balance'])}\n\n"
            f"**Minimum protected:** "
            f"{money(roles['currency'], roles['minimum_balance'])}\n\n"
            f"**Currency:** `{roles['currency']}`\n\n"
            f"**Request type:** `{request_type}`\n\n"
            f"**Description:** {description}\n\n"
            f"**Proposed payments:** "
            f"{plan['count'] if plan['count'] else 'None'}\n\n"
            f"**Frequency:** "
            f"{plan['frequency'] or 'None'}\n\n"
            f"**Agent:** {gemini_state}"
        )

        result = (
            f"### {emoji} {status.replace('_', ' ').upper()}\n\n"
            f"**Requested:** "
            f"{money(roles['currency'], roles['requested_amount'])}\n\n"
            f"**Safe to pay today:** "
            f"{money(roles['currency'], decision['safe'])}\n\n"
            f"**Recommended method:** `{decision['method']}`\n\n"
            f"**Payment plan:** {decision['plan']}\n\n"
            f"**Earliest full payment:** `{earliest}`\n\n"
            f"**Spending changes:** {decision['spending']}\n\n"
            f"**Explanation:** {decision['explanation']}\n\n"
            f"### Guardrails\n\n"
            f"{guardrails}"
        )

        return (
            agent_state,
            roles.get("requested_amount"),
            decision["safe"],
            decision["method"],
            decision["plan"],
            earliest,
            decision["spending"],
            result,
        )

    except Exception as exc:
        return (
            "### Application error\n\n"
            f"`{type(exc).__name__}: {exc}`",
            None,
            None,
            None,
            None,
            None,
            None,
            "The request could not be processed.",
        )


def render_missing(message, roles=None, plan=None, gemini=None):
    roles = roles or {}
    plan = plan or {}

    state = (
        f"### NEEDS INPUT\n\n"
        f"{message}\n\n"
        f"Detected balance: `{roles.get('balance', 'unknown')}`\n\n"
        f"Detected minimum: `{roles.get('minimum_balance', 'unknown')}`\n\n"
        f"Detected request amount: "
        f"`{roles.get('requested_amount', 'unknown')}`\n\n"
        f"Detected currency: `{roles.get('currency', 'unknown')}`\n\n"
        f"Detected plan: "
        f"`{plan.get('count') or 'none'} "
        f"{plan.get('frequency') or ''}`"
    )

    return (
        state,
        None,
        None,
        None,
        "none",
        "N/A",
        "None",
        (
            "Please provide the missing financial information. "
            "The agent will not invent it."
        ),
    )


# ============================================================
# EXISTING DATASET VIEW
# ============================================================

def load_existing():
    if not OUTPUT_CSV.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(OUTPUT_CSV)
    except Exception:
        return pd.DataFrame()


existing_df = load_existing()


# ============================================================
# GRADIO UI
# ============================================================

with gr.Blocks(
    title="Buy or Wait?",
) as demo:

    gr.Markdown(
        """
# 💰 Buy or Wait?

### AI financial affordability agent

**Gemini understands the request.**  
**The deterministic financial layer makes the financial decision.**

For a custom request, put your financial situation and purchase request into
**one natural-language message**.
"""
    )

    with gr.Tabs():

        # ----------------------------------------------------
        # EXISTING REQUESTS
        # ----------------------------------------------------


        # ----------------------------------------------------
        # EXISTING REQUESTS
        # ----------------------------------------------------

        with gr.Tab("Existing request"):

            gr.Markdown(
                "Browse the generated affordability decisions. "
                "Use the search box or select a request to inspect the full decision."
            )

            existing_search = gr.Textbox(
                label="Search requests",
                placeholder="Search request ID, status, payment method...",
            )

            display_columns = [
                "request_id",
                "amount_safe_to_pay",
                "affordability_status",
                "recommended_payment_method",
                "payment_plan",
                "earliest_date_for_full_payment",
            ]

            def filter_existing(query):
                if existing_df.empty:
                    return existing_df

                q = str(query or "").strip().lower()

                if not q:
                    return existing_df[display_columns]

                mask = existing_df.astype(str).apply(
                    lambda column: column.str.lower().str.contains(
                        q,
                        regex=False,
                        na=False,
                    )
                ).any(axis=1)

                return existing_df.loc[
                    mask,
                    display_columns,
                ]

            existing_table = gr.Dataframe(
                value=(
                    existing_df[display_columns]
                    if not existing_df.empty
                    else existing_df
                ),
                headers=display_columns,
                datatype=[
                    "str",
                    "number",
                    "str",
                    "str",
                    "str",
                    "str",
                ],
                interactive=False,
                wrap=False,
                column_widths=[
                    "12%",
                    "14%",
                    "15%",
                    "17%",
                    "25%",
                    "17%",
                ],
                max_height=520,
            )

            request_choices = (
                existing_df["request_id"]
                .astype(str)
                .tolist()
                if not existing_df.empty
                else []
            )

            existing_request_selector = gr.Dropdown(
                label="Inspect a request",
                choices=request_choices,
                value=(
                    request_choices[0]
                    if request_choices
                    else None
                ),
            )

            existing_detail = gr.Markdown(
                value="Select a request to see the complete decision."
            )

            def show_existing_request(request_id):
                if (
                    not request_id
                    or existing_df.empty
                ):
                    return "Select a request to see the complete decision."

                rows = existing_df[
                    existing_df["request_id"].astype(str)
                    == str(request_id)
                ]

                if rows.empty:
                    return "Request not found."

                row = rows.iloc[0]

                def clean(value):
                    if pd.isna(value):
                        return "N/A"
                    return str(value)

                return f"""
### Request `{clean(row.get("request_id"))}`

**Affordability status:** `{clean(row.get("affordability_status"))}`

**Safe amount:** `{clean(row.get("amount_safe_to_pay"))}`

**Recommended payment method:** `{clean(row.get("recommended_payment_method"))}`

**Payment plan:** `{clean(row.get("payment_plan"))}`

**Earliest full payment:** `{clean(row.get("earliest_date_for_full_payment"))}`

**Spending changes needed:**  
{clean(row.get("spending_changes_needed"))}

### Decision explanation

{clean(row.get("decision_explanation"))}
"""

            existing_search.change(
                fn=filter_existing,
                inputs=existing_search,
                outputs=existing_table,
            )

            existing_request_selector.change(
                fn=show_existing_request,
                inputs=existing_request_selector,
                outputs=existing_detail,
            )

            if request_choices:
                existing_detail.value = show_existing_request(
                    request_choices[0]
                )
        with gr.Tab("Ask your own request"):

            gr.Markdown(
                """
### Tell the agent what is going on

Example:

> I have ZAR 30,000 in my account and want to keep ZAR 5,000 untouched.
> I'm considering a ZAR 33,114 laptop. I can pay it in 3 monthly installments.
"""
            )

            request_text = gr.Textbox(
                label="Your financial situation + request",
                placeholder=(
                    "I have ZAR 30,000 in my account and want to keep "
                    "ZAR 5,000 untouched. I'm considering a ZAR 33,114 "
                    "laptop. I can pay it in 3 monthly installments."
                ),
                lines=6,
            )

            analyze_button = gr.Button(
                "Analyze with AI",
                variant="primary",
            )

            gr.Markdown("### Optional advanced fields")

            gr.Markdown(
                "Use these only to correct or complete missing information. "
                "They are not required when the same information is in your message."
            )

            with gr.Row():
                balance_override = gr.Textbox(
                    label="Current balance override",
                    placeholder="e.g. 30000",
                )

                minimum_override = gr.Textbox(
                    label="Minimum protected override",
                    placeholder="e.g. 5000",
                )

                currency_override = gr.Textbox(
                    label="Currency override",
                    placeholder="e.g. ZAR",
                )

            with gr.Row():
                date_override = gr.Textbox(
                    label="Completion date override",
                    placeholder="YYYY-MM-DD",
                )

                income_override = gr.Textbox(
                    label="Known future income override",
                    placeholder="e.g. 15000",
                )

                expense_override = gr.Textbox(
                    label="Known future expense override",
                    placeholder="e.g. 5000",
                )

            gr.Markdown("### Agent understanding")

            agent_state = gr.Markdown()

            with gr.Row():
                detected_amount = gr.Number(
                    label="Detected request amount",
                    interactive=False,
                )

                safe_amount = gr.Number(
                    label="Safe amount",
                    interactive=False,
                )

                recommended_method = gr.Textbox(
                    label="Recommended method",
                    interactive=False,
                )

            with gr.Row():
                payment_plan = gr.Textbox(
                    label="Payment plan",
                    interactive=False,
                )

                earliest_payment = gr.Textbox(
                    label="Earliest full payment",
                    interactive=False,
                )

            spending_changes = gr.Textbox(
                label="Spending changes",
                interactive=False,
            )

            result = gr.Markdown()

            analyze_button.click(
                fn=analyze_custom,
                inputs=[
                    request_text,
                    balance_override,
                    minimum_override,
                    currency_override,
                    date_override,
                    income_override,
                    expense_override,
                ],
                outputs=[
                    agent_state,
                    detected_amount,
                    safe_amount,
                    recommended_method,
                    payment_plan,
                    earliest_payment,
                    spending_changes,
                    result,
                ],
            )


if __name__ == "__main__":
    demo.launch()
