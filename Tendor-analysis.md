You are a Senior Software Architect, AI/LLM Engineer, and Cloud Infrastructure Engineer.

Analyze the ENTIRE existing Smart Tender System repository/codebase. Do NOT rewrite, refactor, or modify any code. Your task is to perform a complete architecture, complexity, scalability, API/model, and monthly operating-cost assessment.

IMPORTANT:
- Inspect the actual repository before making conclusions.
- Do not assume components exist unless you find them in the code.
- Reference actual files, classes, functions, database tables, APIs, and dependencies.
- Clearly separate CURRENT implementation from RECOMMENDED architecture.
- If something cannot be determined from the repository, mark it as "Unknown" and state what information is required.
- Make the recommendation budget-friendly for an Indian company: present recurring costs in INR, show GST separately, use a clearly stated USD/INR planning rate, and prefer an Indian cloud region where data residency or latency requires it.
- Prefer a lean modular-monolith pilot, local/native PDF extraction, conditional open-source OCR, local embeddings, content deduplication, caching, and asynchronous batch work before introducing paid managed services.
- Do not treat a provider free tier as a production SLA and do not recommend Kubernetes, Kafka, OpenSearch, a managed vector database, paid OCR, or multi-region deployment without a measured or contractual need.

SYSTEM OBJECTIVE:
Smart Tender System should support:
1. Tender ingestion/discovery
2. Tender document/PDF downloading
3. PDF text extraction
4. OCR for scanned documents
5. Tender classification
6. BOQ extraction
7. Eligibility/qualification analysis
8. Financial qualification analysis
9. Project/tender matching
10. Risk analysis
11. AI-based tender analysis
12. Search and retrieval across tender documents
13. User-facing tender summaries and recommendations
14. Auditability and evidence/citation tracking

==================================================
1. CURRENT SYSTEM ANALYSIS
==================================================

Analyze:

- Backend architecture
- Frontend architecture
- Database architecture
- API architecture
- Authentication/authorization
- Document storage
- PDF processing
- OCR
- BOQ extraction
- Embedding generation
- Vector database/index
- Retrieval pipeline
- LLM integration
- Background jobs
- Caching
- Logging/monitoring
- Error handling
- Security
- Deployment architecture

Create a component dependency map.

==================================================
2. COMPLEXITY ANALYSIS
==================================================

For every major component determine:

- Computational complexity
- CPU requirements
- RAM requirements
- GPU requirements
- Storage requirements
- Network requirements
- Processing latency
- Expected failure points
- Scalability difficulty

Classify each component as:

LOW / MEDIUM / HIGH / VERY HIGH

Pay special attention to:

PDF extraction
OCR
BOQ extraction
Embedding generation
Vector search
LLM inference/API calls
Large tender processing
Batch processing

==================================================
3. BOTTLENECK ANALYSIS
==================================================

Identify what will become the bottleneck at:

100 tenders/day
1,000 tenders/day
10,000 tenders/day
100,000 tenders/day

Estimate:

- PDFs/day
- pages/day
- OCR workload
- embeddings/day
- vector queries/day
- LLM requests/day
- storage growth/month
- expected processing time

Do not invent exact numbers. Clearly label estimates and assumptions.

==================================================
4. LONG-TERM ARCHITECTURE
==================================================

Design a production-ready architecture:

API Layer
    ↓
Authentication
    ↓
Tender Ingestion
    ↓
Job Queue
    ↓
Document Workers
    ↓
PDF Extraction / OCR
    ↓
BOQ Extraction
    ↓
Chunking + Metadata
    ↓
Embedding Generation
    ↓
Vector + Metadata Storage
    ↓
Hybrid Retrieval
    ↓
Business Rule Engines
    ↓
LLM Tender Analyst
    ↓
Structured Results
    ↓
API / Dashboard

Determine which components should be:

- synchronous
- asynchronous
- worker-based
- independently scalable

Recommend appropriate technologies only where justified by the current codebase.

==================================================
5. LLM / API ANALYSIS
==================================================

Evaluate the current LLM architecture.

Determine whether the system should use:

- API-based LLM
- self-hosted LLM
- hybrid architecture

Evaluate suitable API/model options based on:

- reasoning quality
- long-context capability
- structured outputs
- function/tool calling
- latency
- reliability
- token cost
- scalability
- privacy/data governance
- vendor lock-in

Compare these four API companies explicitly on the same workload assumptions:

- Google Gemini
- OpenAI
- Anthropic Claude
- Groq

For each company include current production model IDs for a low-cost routine tier and a stronger reasoning tier; official input/output price per one million tokens; cost per tender; monthly cost at 100, 1,000, and 10,000 tenders/day; batch/caching availability; latency/quality role; free-tier limitations; privacy/data handling considerations; and suitability for Indian production billing. Show USD list prices and converted INR. Do not compare unlike workloads or imply equal model quality merely because token counts match.

For OpenAI specifically, evaluate the Responses API and appropriate model tiers.

Design an abstraction such as:

LLMProvider
    ├── GeminiProvider
    ├── GroqProvider
    ├── OpenAIProvider
    ├── ClaudeProvider
    └── LocalModelProvider (optional)

The application should not be tightly coupled to one LLM vendor.

==================================================
6. RETRIEVAL ARCHITECTURE
==================================================

Analyze the current RAG pipeline.

Evaluate:

- embedding model
- chunk size
- overlap
- metadata
- vector index
- metadata filtering
- keyword search
- semantic search
- hybrid retrieval
- reranking
- top-k
- citation/provenance
- duplicate handling
- document versioning

Recommend the long-term retrieval architecture.

IMPORTANT:

Do NOT send complete tender documents to the LLM unnecessarily.

Use:

User Query
→ Retrieval
→ Relevant Tender Sections
→ Relevant BOQ/Eligibility Data
→ Evidence
→ LLM Reasoning
→ Structured Answer

==================================================
7. BUSINESS LOGIC
==================================================

Determine which parts should be deterministic rather than LLM-driven.

Evaluate:

Project Matching Engine
Financial Qualification Engine
Risk Analysis Engine
Eligibility Engine
BOQ Analysis
Tender Scoring

Clearly identify:

RULE-BASED LOGIC
vs
ML/EMBEDDING LOGIC
vs
LLM REASONING

The LLM must not become the system of record for financial or contractual facts.

==================================================
8. DATABASE & STORAGE
==================================================

Analyze current database design.

Recommend long-term separation of:

- relational metadata
- tender documents
- extracted text
- BOQ data
- embeddings
- analysis results
- audit logs

Evaluate:

PostgreSQL
Object Storage
Vector Database
Redis/cache

Only recommend migration if there is a measurable architectural reason.

==================================================
9. COST ANALYSIS
==================================================

Estimate monthly operating cost for:

A. Development
B. Small production
C. Medium production
D. Enterprise scale

Include:

- Compute
- Database
- Object storage
- Vector database
- Redis/cache
- OCR
- LLM/API
- Embeddings
- Monitoring
- Backup
- Network

Create a table:

Component | Monthly Minimum | Normal | High Scale

Also calculate estimated total monthly cost for:

100 tenders/day
1,000 tenders/day
10,000 tenders/day

Clearly state all assumptions.

The primary budget must be in INR for an India-first deployment. State a conservative planning exchange rate, keep GST and payment/foreign-exchange charges separate, and distinguish:

- development/free-tier cost;
- lean controlled pilot cost;
- production cost with backups and monitoring;
- high-availability/enterprise cost.

Include a provider sensitivity table for Gemini-only, OpenAI-only, Claude-only, Groq-only, and a recommended hybrid route. Include local/open-source OCR versus paid OCR sensitivity because OCR may cost more than the LLM.

Do NOT include developer salaries unless separately requested.

==================================================
10. COST OPTIMIZATION
==================================================

Identify how to minimize recurring cost through:

- retrieval-first LLM calls
- caching
- batching
- asynchronous processing
- cheaper models for routine tasks
- expensive models only for complex reasoning
- embedding reuse
- OCR only when required
- document deduplication
- prompt/token optimization
- autoscaling
- local native-text extraction before OCR
- open-source OCR with paid fallback only for low-confidence pages
- local embeddings where retrieval quality is acceptable
- INR spend limits and premium-model approval gates

==================================================
11. SECURITY
==================================================

Analyze:

- API security
- authentication
- authorization
- tenant isolation
- document access
- encryption
- secrets management
- audit logs
- prompt injection
- malicious PDF risks
- data leakage
- LLM provider data handling

==================================================
12. OBSERVABILITY
==================================================

Recommend monitoring for:

- API latency
- queue latency
- PDF processing time
- OCR failures
- extraction failures
- embedding latency
- retrieval quality
- LLM latency
- token usage
- LLM cost
- failed jobs
- database performance

==================================================
13. FINAL ARCHITECTURE RECOMMENDATION
==================================================

Produce:

1. Current Architecture
2. Current Complexity
3. Major Bottlenecks
4. Scalability Assessment
5. Recommended Long-Term Architecture
6. Recommended API/LLM Strategy
7. Recommended Retrieval Strategy
8. Recommended Database/Storage Strategy
9. Recommended Async/Worker Strategy
10. Security Recommendations
11. Monitoring Recommendations
12. Monthly Infrastructure Cost
13. Cost Optimization Strategy
14. Migration Roadmap

Use:

P0 = Required before production
P1 = Required for scale
P2 = Future optimization

==================================================
14. CLIENT-FACING SUMMARY
==================================================

At the end create a concise section titled:

"Smart Tender System — Technical & Cost Summary"

Maximum 1–2 pages.

It must contain:

- System overview
- Recommended architecture
- Recommended API/model strategy
- Scalability approach
- Minimum monthly infrastructure cost
- Expected production cost range
- Major assumptions
- Key technical recommendations
- India-first monthly budget before and after GST
- Gemini vs OpenAI vs Claude vs Groq API cost comparison

Use professional language suitable for submitting directly to a client.

==================================================
OUTPUT FILES
==================================================

Create:

1. smart_tender_architecture_assessment.md
2. smart_tender_cost_estimation.md
3. smart_tender_client_summary.md

Do not modify existing application code.

Keep this `Tendor-analysis.md` assessment brief aligned with the three generated documents so future reruns preserve the India-first, cost-controlled assumptions.
