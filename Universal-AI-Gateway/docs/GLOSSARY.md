# 📖 Project Glossary

Definitions for domain-specific terminology and technical acronyms used throughout the Universal LLM Gateway.

## A

- **API Key Hashing**: The process of applying a one-way mathematical function (Argon2id) to an API key so the plain text is never stored in the database.
- **Argon2id**: A modern, security-hardened password/key hashing algorithm designed to resist GPU and ASIC-based brute force attacks.

## C

- **Circuit Breaker**: A design pattern that detects provider failures and "opens" the circuit to prevent the application from making useless calls to a down service.
- **Cosine Similarity**: A metric used to measure how similar two vectors are. Used in **Semantic Caching** to find related prompts.

## E

- **Ensemble (Racing)**: A technique where multiple LLMs are called at the same time for the same prompt, and the fastest response is used.

## G

- **Gemini**: Google's frontier LLM family, supported as a core provider via the Universal Gateway adapter.
- **Guardrails**: Integrated safety features (PII redaction, prompt safety) that protect the gateway and its users from data leaks and malicious prompts.

## O

- **OpenTelemetry (OTel)**: A standardized observability framework used for generating and collecting distributed traces and metrics.

## R

- **RediSearch**: A Redis module that provides full-text and vector search capabilities. Powering our **Semantic Cache**.

## S

- **Notifier**: An internal service that dispatches alerts to external webhooks (e.g., Slack, PagerDuty) for budget and circuit events.
- **Semantic Distance**: The inverse of similarity; a measure of how "far apart" two concepts are in a vector space.

## T

- **Tenant**: A logical grouping of users/keys (e.g., an organization or department) that shares a common budget and rate limit.
- **Token Bucket**: An algorithm used for rate limiting that allows for bursts while maintaining a steady average throughput.
