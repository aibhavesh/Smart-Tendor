# Smart Tender System — India-First Technical & Cost Summary

**Prepared:** 16 September 2026  
**Budget basis:** INR, ₹90/US$ planning rate, before GST

## System overview

The Smart Tender System is a strong pilot foundation built with FastAPI, Next.js, PostgreSQL, Qdrant, PDF/BOQ extraction, project matching, role-based access, audit logs, deterministic qualification/risk engines, and Gemini-based narratives. Its most important safety feature is that business rules—not an LLM—control financial qualification and the official verdict. That principle should remain unchanged.

It is not yet ready for high-volume production. Downloads run inside the web process, documents use local disk, scanned-document OCR and tender-document RAG are absent, and there is no durable job queue, evidence/version model, or tenant isolation. Reports can also be regenerated when read, repeating latency and API cost.

## Recommended cost-friendly architecture

Retain the current FastAPI, Next.js, PostgreSQL, Qdrant, and domain engines. A rewrite or early microservice/Kubernetes programme would add cost without solving the immediate risks.

```text
Web/API → authentication → durable job record/queue
        → safe download → low-cost object storage
        → native PDF text first → local OCR only when needed
        → BOQ/fact extraction → chunks + evidence
        → local embeddings + hybrid search
        → deterministic rules → budget-aware LLM router
        → stored result, citations, audit, and dashboard
```

For the pilot, use one modest API/worker VM in an acceptable Indian region, a separate PostgreSQL/backup boundary, S3-compatible object storage, and the current self-hosted Qdrant. PostgreSQL job/outbox tables are sufficient initially; add Redis, managed vector search, Kafka, Kubernetes, and multi-region infrastructure only when measured demand or a contract requires them.

Native text extraction, Tesseract/PaddleOCR-style local OCR, local BGE embeddings, content-hash deduplication, and stored reports eliminate the largest avoidable API charges. Paid OCR should handle only low-confidence pages or difficult BOQ tables.

## AI API comparison

All costs below apply the same assumed workload: 25K input + 4K output routine tokens per tender, plus a 20% chance of 12K input + 2K output complex work. They compare price, not equivalent quality.

| Provider | Routine / complex models | Approx. API cost per tender | Approx. API cost at 100 tenders/day |
|---|---|---:|---:|
| Groq | GPT-OSS 20B / 120B | **₹0.33** | **₹992/month** |
| OpenAI | GPT-5.6 Luna / Terra | ₹1.75 | ₹5,238/month |
| Google Gemini | Gemini 3.5 Flash-Lite / 3.8 Flash | ₹1.87 | ₹5,616/month |
| Anthropic Claude | Haiku 4.5 / Sonnet 5 | ₹4.84 | ₹14,526/month |
| Recommended hybrid | Groq routine + Gemini complex | **₹0.57** | **₹1,721/month** |

Rates were checked against the official [Gemini](https://ai.google.dev/gemini-api/docs/pricing), [OpenAI](https://developers.openai.com/api/docs/models), [Claude](https://platform.claude.com/docs/en/about-claude/pricing), and [Groq](https://console.groq.com/docs/models) pages on the prepared date. They are list prices and can change.

Recommended policy:

- keep Gemini first during initial deployment because the repository already supports it;
- add Groq for high-volume routine classification, schema repair, and short summaries after accuracy testing;
- use Gemini, OpenAI, or Claude only for ambiguous, high-value cases;
- use deterministic code and human review for the final financial/eligibility decision;
- use batch APIs for non-urgent work where available;
- record and cap tokens, retries, provider cost, and premium-model escalations.

Model choice must be configuration, not hard-coded business logic. Every provider should implement the same `LLMProvider` contract and return structured output, model/version, token usage, latency, cost, and safe error information. Tender evidence sent to any external provider must pass the company’s privacy, retention, and data-residency review.

## Scalability approach

The immediate bottleneck is reliable document processing, not the website. At scale, scanned-page OCR, BOQ extraction, queue delay, provider quotas, and retained vectors dominate.

| Throughput | Pages/day | New vectors/day | Gross new storage/month | Main action |
|---:|---:|---:|---:|---|
| 100 tenders/day | 10,000 | 8,800 | 75 GB | safe pilot and measured cost/quality |
| 1,000/day | 1,00,000 | 88,000 | 750 GB | separate workers; stronger DB/backups |
| 10,000/day | 10,00,000 | 8,80,000 | 7.5 TB | autoscaled pools and negotiated quotas |

Use asynchronous, idempotent workers with leases, retries, and dead-letter handling. Every extracted fact and AI claim should point to the exact document version and page. Retrieve only the best 6–12 evidence sections instead of sending complete tender documents.

## Monthly India budget

Figures exclude salaries, implementation, paid tender feeds, premium support, and GST.

| Environment | Expected monthly total | What it means |
|---|---:|---|
| Development/demo | **₹0–₹5,000** | free/local services and strict API caps; no SLA |
| Controlled production pilot, ~100/day | **₹8,000–₹25,000** | lean single-region platform, local OCR/embeddings, hybrid AI routing |
| Medium production, ~1,000/day | **₹50,000–₹1,50,000** | separate worker capacity, stronger DB/storage/monitoring |
| High volume, ~10,000/day | **₹4,00,000–₹10,00,000** | load-tested cluster and negotiated provider capacity |

At 100 tenders/day, using every baseline OCR page with a paid cloud OCR service could add roughly ₹32,400/month by itself. That is why conditional local OCR is the primary cost decision. If 18% GST applies, a ₹20,000 pre-tax invoice becomes ₹23,600; actual GST/overseas SaaS treatment should be confirmed by the company’s accountant.

These are planning ranges, not quotations. Availability, retention, scanned-page rate, table complexity, user concurrency, Indian-region vendor, exchange rate, and invoice tax treatment can materially change them.

## Delivery priorities

**P0 — before production**

1. Add object storage, durable jobs/outbox, independent workers, retries, dead-letter handling, and backups.
2. Stream and sandbox PDF ingestion; close SSRF and malicious-file paths.
3. Add page-aware native extraction, conditional local OCR, BOQ evidence, confidence, and review.
4. Persist reports and analysis versions; a page refresh must not create a new AI charge.
5. Add rupee budgets, token limits, cost telemetry, stronger sessions/MFA/rate limits, and restore testing.

**P1 — after pilot measurements**

1. Add hybrid retrieval, reranking, citations, and an evaluation set using real Indian tenders.
2. Add Groq/OpenAI/Claude adapters behind the existing provider interface and use quality-gated routing.
3. Separate and autoscale worker stages only where queue age or throughput proves the need.

**P2 — only with measured justification**

Self-host a larger LLM, buy a managed vector platform, adopt Kubernetes, or deploy multi-region only when sustained utilisation, privacy requirements, or contractual availability makes the additional cost worthwhile.

## Recommendation

Proceed with the current codebase as the pilot foundation. Budget **₹8,000–₹25,000/month before GST for about 100 tenders/day**, start with the existing Gemini integration, and introduce the Groq + Gemini hybrid only after it passes extraction, citation, and decision-consistency tests. This preserves quality and auditability while keeping recurring Indian operating cost under control.
