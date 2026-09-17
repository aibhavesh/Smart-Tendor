# Smart Tender System — India-First Monthly Cost Estimate

**Estimate date:** 16 September 2026  
**Currency:** Indian rupees (INR), before GST and implementation/support fees  
**Planning exchange rate:** **₹90 per US$1**. This is a budgeting assumption, not a live foreign-exchange quote.  
**Architecture priced:** The cost-optimised architecture in [`smart_tender_architecture_assessment.md`](smart_tender_architecture_assessment.md).

## 1. Recommended cost posture

For an Indian SME or pilot, the economical design is not “send every PDF page to a paid AI service.” It is:

1. extract native PDF text locally;
2. run open-source OCR only on pages with missing or poor text;
3. run layout/table extraction only on likely BOQ pages;
4. deduplicate and store the result once;
5. retrieve only the relevant clauses and facts;
6. use a low-cost model for routine structured work;
7. escalate only ambiguous, high-value cases to a stronger model;
8. cache the final report so reopening a tender does not create another bill.

This approach can support a controlled production pilot near **₹8,000–₹25,000/month before GST** at roughly 100 tenders/day. The lower end accepts a self-managed single-region setup and modest support; it is not an enterprise SLA.

## 2. Workload assumptions

These are planning assumptions, not repository facts. Replace them with measured pilot data.

| Assumption | Baseline |
|---|---:|
| PDFs per tender | 2 |
| Pages per PDF | 50 |
| Pages per tender | 100 |
| Pages needing OCR | 30% |
| Pages needing structured table/BOQ extraction | 5% |
| Original plus derived storage | 25 MB/tender |
| Embedding input | 70,000 tokens/tender |
| Routine LLM workload | 25,000 input + 4,000 output tokens/tender |
| Complex LLM workload | 20% × (12,000 input + 2,000 output tokens) |
| Expected LLM calls | about 3.2/tender |
| Month | 30 days |

The model comparison below uses the same token workload for every provider. It therefore compares list-price arithmetic, not model quality. A cheaper model that needs retries or produces incorrect tender facts can cost more per accepted result.

## 3. API price comparison: Gemini, OpenAI, Claude, and Groq

### 3.1 Published model rates used

Rates are public list prices per one million tokens (MTok), in USD, checked on the estimate date. Prices, model availability, taxes, quotas, and promotional periods can change; verify them before purchase.

| Company/API | Routine model | Input / output per MTok | Complex model | Input / output per MTok | Position in this design |
|---|---|---:|---|---:|---|
| Google Gemini | Gemini 3.5 Flash-Lite | $0.30 / $2.50 | Gemini 3.8 Flash | $0.75 / $3.75 through 31 Dec 2026 | Good low-cost multimodal option; existing provider reduces implementation effort |
| OpenAI | GPT-5.6 Luna | $0.20 / $1.20 | GPT-5.6 Terra | $2.00 / $12.00 | Strong structured-output and tool ecosystem; use as a quality fallback |
| Anthropic Claude | Claude Haiku 4.5 | $1.00 / $5.00 | Claude Sonnet 5 | $2.00 / $10.00 | Premium fallback for difficult clause interpretation after evaluation |
| Groq | GPT-OSS 20B | $0.075 / $0.30 | GPT-OSS 120B | $0.15 / $0.60 | Lowest list-price option here and very fast; validate tender accuracy before making it authoritative |

Official sources:

- [Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [OpenAI API model catalog](https://developers.openai.com/api/docs/models)
- [Claude API pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Groq production models and pricing](https://console.groq.com/docs/models)

Free tiers are suitable for development and evaluation, not for a production budget or SLA. Paid Gemini data is not used to improve Google products according to the pricing page; free-tier handling differs. Provider privacy, retention, residency, and contractual terms still require review before tender content is uploaded.

### 3.2 Like-for-like cost per tender

Formula:

```text
cost/tender = routine input + routine output
              + 20% × (complex input + complex output)
INR cost     = USD cost × ₹90
```

| Provider route | Routine cost | Expected complex cost | Total per tender | Total per tender (INR) |
|---|---:|---:|---:|---:|
| Gemini only | $0.01750 | $0.00330 | $0.020800 | **₹1.87** |
| OpenAI only | $0.00980 | $0.00960 | $0.019400 | **₹1.75** |
| Claude only | $0.04500 | $0.00880 | $0.053800 | **₹4.84** |
| Groq only | $0.003075 | $0.000600 | $0.003675 | **₹0.33** |
| Recommended hybrid: Groq routine + Gemini complex | $0.003075 | $0.003300 | $0.006375 | **₹0.57** |

The hybrid route is the planning recommendation because it keeps routine cost low while retaining Gemini for harder cases and requiring only one additional provider implementation beyond the repository’s existing Gemini adapter. It must be gated by an evaluation set; if Groq does not meet extraction and citation targets, use Gemini or OpenAI for that use case.

### 3.3 Monthly LLM cost under the baseline

Before GST, retries, foreign-exchange/card fees, grounding/search tool charges, and provider-specific extras:

| Tenders/day | Tenders/month | Gemini | OpenAI | Claude | Groq | Recommended hybrid |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 3,000 | ₹5,616 | ₹5,238 | ₹14,526 | ₹992 | **₹1,721** |
| 1,000 | 30,000 | ₹56,160 | ₹52,380 | ₹1,45,260 | ₹9,923 | **₹17,213** |
| 10,000 | 3,00,000 | ₹5,61,600 | ₹5,23,800 | ₹14,52,600 | ₹99,225 | **₹1,72,125** |

Gemini, OpenAI, and Claude publish approximately 50% batch discounts for eligible asynchronous inference. Do not apply that discount to interactive requests or assume an equivalent Groq discount without a current written price. Prompt caching may reduce repeated-input cost, but the table does not assume a cache hit rate.

### 3.4 Recommended routing policy

| Work | Default | Escalation | Reason |
|---|---|---|---|
| Classification, schema repair, short summaries | Groq GPT-OSS 20B | Gemini Flash-Lite | cheapest repeatable work |
| Clause/eligibility ambiguity | Gemini 3.8 Flash | OpenAI Terra or Claude Sonnet | quality matters more than a fraction of a rupee |
| Final financial calculation or eligibility verdict | deterministic code | human review | LLM must not be the system of record |
| Offline bulk analysis | provider batch API where supported | standard API only when urgent | can reduce eligible token cost |
| Sensitive tender content | redacted API input or approved local model | human workflow | governance before convenience |

## 4. OCR: the largest avoidable cost

Use local native-text extraction first, followed by Tesseract/PaddleOCR or an equivalent open-source OCR worker. Paid OCR should be a fallback only for low-confidence pages or difficult BOQ tables.

For comparison, applying the previously assessed AWS Textract list rates to every baseline OCR/table page would be approximately:

| Tenders/day | Cloud OCR if used on all baseline OCR pages | India-first policy |
|---:|---:|---|
| 100 | about ₹32,400/month | local OCR; keep ₹0–₹3,000 for exceptional-page fallback |
| 1,000 | about ₹3,24,000/month | dedicated CPU workers; fallback only after confidence checks |
| 10,000 | about ₹23,67,000/month after volume tiers | benchmark local OCR farm and negotiate fallback pricing |

Local OCR is not “free”: it consumes CPU, storage, operations effort, and may be less accurate on complex tables. Measure field accuracy and human-correction rate. A paid service is justified when its reduction in review effort is worth more than the API charge.

## 5. Other variable costs

### 5.1 Embeddings

Using OpenAI `text-embedding-3-small` at the assessed $0.02/MTok:

| Tenders/day | Tokens/month | API embedding cost at ₹90/US$ |
|---:|---:|---:|
| 100 | 210 million | about ₹378/month |
| 1,000 | 2.1 billion | about ₹3,780/month |
| 10,000 | 21 billion | about ₹37,800/month |

The current local BGE embedding implementation can avoid this API line if quality and throughput are acceptable. Reuse vectors by content hash and re-embed only when content or the chosen model version changes.

### 5.2 Object storage

| Tenders/day | New storage/month | Twelve-month gross retained data |
|---:|---:|---:|
| 100 | 75 GB | 900 GB |
| 1,000 | 750 GB | 9 TB |
| 10,000 | 7.5 TB | 90 TB |

Actual cost depends on the Indian region/provider, request count, egress, replicas, versioning, and lifecycle tier. Store originals once, compress derivatives, and archive superseded files. Do not keep rendered pages or debug artifacts indefinitely.

## 6. India-first platform budget

The ranges below are provider-neutral planning allowances. Obtain quotes for an Indian region where residency or latency requires it. “Lean pilot” deliberately avoids Kubernetes, Kafka, OpenSearch, a managed vector database, and multi-region deployment.

| Component | Development/demo | Lean pilot (~100/day) | Medium (~1,000/day) |
|---|---:|---:|---:|
| Frontend/CDN | ₹0–₹500 | ₹0–₹1,000 | ₹1,000–₹3,000 |
| API and worker compute | ₹0–₹1,500 | ₹3,500–₹8,000 | ₹15,000–₹45,000 |
| PostgreSQL | ₹0–₹500 | ₹1,500–₹4,000 | ₹6,000–₹18,000 |
| Object storage and backup | ₹0–₹300 | ₹500–₹1,500 | ₹2,500–₹8,000 |
| Vector search | ₹0 | ₹0–₹1,500 | ₹3,000–₹15,000 |
| Queue/cache | ₹0 | ₹0–₹1,000 | ₹1,000–₹5,000 |
| OCR compute/fallback reserve | ₹0–₹500 | ₹0–₹3,000 | ₹3,000–₹15,000 |
| Monitoring, network, domain, email | ₹0–₹500 | ₹500–₹2,000 | ₹2,000–₹8,000 |
| LLM API | usage based | see comparison | see comparison |

Cost-friendly implementation choices:

- serve the Next.js frontend from a free/low-cost static or edge tier where compatible;
- use one app/worker VM for the pilot and a separate database/backup boundary;
- use PostgreSQL job/outbox tables initially; add Redis only when measured queue/cache load requires it;
- keep the existing self-hosted Qdrant for the pilot or benchmark PostgreSQL `pgvector`; do not buy a managed vector cluster by default;
- use S3-compatible object storage in an acceptable region instead of local application disk;
- use local PDF extraction, OCR, and embeddings before paid services;
- scale workers on queue age and shut down non-production workers outside working hours.

## 7. Monthly total by scale

These totals are **before GST** and exclude salaries, implementation, paid tender feeds, SMS/WhatsApp volume, compliance certification, premium support, and disaster-recovery regions.

| Scale | Lean fixed platform | LLM route | Expected monthly total | Practical interpretation |
|---|---:|---:|---:|---|
| Development/demo | ₹0–₹3,000 | free tier or capped usage | **₹0–₹5,000** | no production SLA |
| 100 tenders/day | ₹6,000–₹18,000 | hybrid ≈ ₹1,721 | **₹8,000–₹25,000** | recommended controlled pilot budget |
| 1,000/day | ₹35,000–₹1,20,000 | hybrid ≈ ₹17,213 | **₹50,000–₹1,50,000** | separate workers and stronger DB/backup |
| 10,000/day | ₹2,50,000–₹8,00,000 | hybrid ≈ ₹1,72,125 | **₹4,00,000–₹10,00,000** | load-tested cluster; negotiated services |

Provider sensitivity at 100 tenders/day:

| API choice | Approx. platform + LLM total/month |
|---|---:|
| Groq only | ₹7,000–₹19,000 |
| Recommended Groq + Gemini hybrid | **₹8,000–₹20,000** |
| OpenAI only | ₹11,000–₹24,000 |
| Gemini only | ₹12,000–₹24,000 |
| Claude only | ₹21,000–₹33,000 |

The top-level pilot allowance remains ₹8,000–₹25,000 to cover usage variation and occasional paid OCR. If the business requires high availability, a managed database with point-in-time recovery, 24×7 support, or cross-region disaster recovery, budget above the lean range.

### Tax treatment

Apply **18% GST only where it is actually chargeable** on the supplier invoice. At a ₹20,000 pre-tax budget, 18% GST would make the cash invoice ₹23,600 before foreign-exchange/card fees. GST input credit, TDS/TCS, place-of-supply, and overseas SaaS treatment depend on the customer and invoice; confirm with the company’s accountant. All tables deliberately show pre-tax amounts to avoid mixing tax assumptions into technical unit economics.

## 8. Hard cost controls

1. Set monthly and per-tenant rupee budgets with alerts at 50%, 75%, 90%, and 100%.
2. Cap input/output tokens and the number of retries per use case.
3. Require approval for full reprocessing, premium-model use, and paid OCR above a page threshold.
4. Persist provider/model, input/output/cached tokens, latency, and estimated INR cost for every call.
5. Deduplicate by document hash and cache extraction, embeddings, and final reports by version.
6. Never create a billable LLM report from a read-only GET request.
7. Use only 6–12 retrieved evidence sections, not the complete tender, unless explicitly justified.
8. Re-evaluate provider quality and list prices quarterly; model IDs are configuration, not business logic.

## 9. Information needed for a binding estimate

Collect two to four weeks of representative pilot telemetry:

- tenders/day and burst pattern;
- documents, pages, file sizes, languages, and scanned-page percentage;
- BOQ/table pages and OCR correction rate;
- extraction and OCR CPU-seconds per page;
- input/output tokens, retries, cache hits, and escalations per use case;
- users, searches, and regenerated reports per tender;
- retention, backup, region, residency, RPO/RTO, and availability requirements;
- provider invoices including GST, foreign-exchange fees, and any negotiated discount.

The pilot data should decide the final cloud/provider bill of materials. The figures above are a transparent planning model, not a vendor quotation.
