Buy or Wait? — AI Financial Affordability Agent

An AI-assisted financial affordability agent for the HackerRank Orchestrate September 2026 challenge.

The core design is deliberately split into two responsibilities:

Gemini understands the request and unstructured evidence.
The deterministic financial engine makes the affordability decision.

This separation keeps the final financial decision reproducible, testable, and protected from LLM hallucination.

1. Problem

The agent evaluates whether a user can safely make a requested financial commitment while preserving required balances, protected/essential spending, known future cash flows, and any eligible payment options.

For the benchmark dataset, the system produces one row per request in dataset/output.csv.

For the interactive demo, a user can describe their financial situation and purchase request in one natural-language message, for example:

I have ZAR 30,000 in my account and want to keep ZAR 5,000 untouched. I'm considering a ZAR 33,114 laptop. I can pay it in 3 monthly installments.

The demo extracts the financial facts, validates missing information, and sends the normalized state to the deterministic decision layer.

2. Architecture

                         ┌─────────────────────┐
                         │   User / Dataset    │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │ Request + evidence  │
                         │ retrieval/understand│
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │       Gemini        │
                         │ Understanding only │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │ Validation /        │
                         │ normalization       │
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │ Deterministic       │
                         │ financial engine     │
                         └──────────┬──────────┘
                                    │
                  ┌─────────────────┼─────────────────┐
                  │                 │                 │
          affordability      payment method    payment schedule
                  │                 │                 │
                  └─────────────────┼─────────────────┘
                                    │
                         ┌──────────▼──────────┐
                         │     output.csv      │
                         └─────────────────────┘

Gemini's role

Gemini is used as an interpretation layer for natural language and unstructured evidence. It can identify facts such as amounts, descriptions, dates, and other request-related information.

Gemini does not have final authority over affordability.

Deterministic financial engine

The deterministic engine is responsible for the financial decision. It evaluates the normalized financial state, protected minimum balance, projected cash flows, request amount, and eligible payment options.

This provides a stable decision boundary:

LLM -> interpretation
Code -> financial decision

3. Guardrails

The implementation uses several safeguards around the LLM layer:

Financial decisions are not delegated to Gemini.

Missing essential financial information is requested instead of invented.

Current balance and requested purchase amount are treated as separate concepts.

A protected minimum balance is enforced.

Currency consistency is checked before financial evaluation.

Installment plans are considered only when a payment count is explicitly supplied.

Financing fees are not invented when they are not explicitly available.

Gemini/API failures can fall back to deterministic request understanding so the application remains usable.

Benchmark output is validated for schema, row count, unique request IDs, non-negative safe amounts, and non-empty explanations.

4. Benchmark datasets

The challenge data is under dataset/ and includes:

requests.csv

financial_profiles.csv

financial_events.csv

request_payment_options.csv

messages.csv

images.csv

exchange_rates.csv

output.csv

The required output schema is:

request_id
amount_safe_to_pay
affordability_status
recommended_payment_method
payment_plan
earliest_date_for_full_payment
spending_changes_needed
decision_explanation

The output constraint is:

0 <= amount_safe_to_pay <= requested_amount

5. Interactive Gradio demo

app.py provides two modes:

Existing request

Browse decisions generated for the benchmark requests.

Ask your own request

The user can provide financial state and the requested purchase in one natural-language message. Optional fields are available only as overrides/corrections.

Example:

I have ZAR 30,000 in my account and want to keep ZAR 5,000 untouched.
I'm considering a ZAR 33,114 laptop.
I can pay it in 3 monthly installments.

The demo shows the detected financial state, safe amount, recommended method, payment plan, earliest full payment date, spending changes, and explanation.

6. Setup

Requirements

Python 3.10+

A Gemini API key for Gemini-powered request understanding

Create and activate a virtual environment:

python -m venv venv
source venv/bin/activate

Install dependencies:

pip install -r requirements.txt

Create .env from the example:

cp .env.example .env

Set:

GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.5-flash-lite

Never commit .env or an API key.

7. Run the application

Launch the Gradio demo:

python app.py

The local interface is then available at:

http://127.0.0.1:7860

8. Run the benchmark pipeline

The repository also contains the benchmark finance pipeline under code/.

The final benchmark artifact is:

dataset/output.csv

The finance decision layer is deterministic so benchmark results can be reproduced without relying on an LLM to make the final decision.

9. Gemini quota and failure handling

The application treats Gemini as an external dependency rather than a single point of failure.

The runtime architecture includes:

server-side API-key loading

caching of successful evidence extraction

bounded request execution

retry/backoff for transient failures

quota/API failure detection

deterministic fallback behavior

This is especially important for free-tier/API quota exhaustion: the financial decision layer must continue to operate on whatever validated information is available rather than repeatedly retrying an exhausted provider quota.

10. Project structure

.
├── app.py
├── code/
│   ├── agents/
│   │   ├── gemini/
│   │   └── runtime/
│   └── finance/
│       └── v4/
├── dataset/
│   ├── requests.csv
│   ├── financial_profiles.csv
│   ├── financial_events.csv
│   ├── request_payment_options.csv
│   ├── messages.csv
│   ├── images.csv
│   ├── exchange_rates.csv
│   └── output.csv
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt

11. Design principle

The central design decision is simple:

Use AI where interpretation is difficult; use deterministic code where correctness matters.

Gemini is useful for understanding language and unstructured evidence. The affordability decision remains deterministic so that the system can be tested, reasoned about, and defended during evaluation.