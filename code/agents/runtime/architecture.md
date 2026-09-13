# Agent Runtime Architecture

The affordability agent separates AI interpretation from financial authority.

## Request path

Customer request
→ evidence cache
→ agent queue
→ Gemini worker
→ evidence validation
→ deterministic V4 financial engine
→ final response.

## Scaling

The service should use:

- API/load-balancing layer for application instances.
- Queue for decoupling customer traffic from model capacity.
- Bounded workers to respect provider RPM/TPM/RPD limits.
- Evidence caching to avoid repeated model calls.
- Retry with exponential backoff for transient failures.
- Immediate fallback for daily quota exhaustion.
- Deterministic financial engine as the final authority.

A load balancer distributes application traffic but does not increase a Gemini project's provider quota.

## Safety boundary

Gemini may interpret unstructured evidence.

Gemini may not:

- modify an existing financial event,
- modify profile state,
- override minimum-balance rules,
- determine the numerical safe amount,
- override the deterministic financial engine.

When Gemini is unavailable, the deterministic engine continues from structured financial data.
