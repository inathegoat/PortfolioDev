# Second Brain

**Local, evaluated, secure, modular RAG system.**  
Index your documents, answer with exact citations, detect injections.

[![CI](https://github.com/user/second-brain/actions/workflows/ci.yml/badge.svg)](https://github.com/user/second-brain/actions)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Quick Demo

```bash
# 1. Ingest a document
python main.py ingest

# 2. Ask a question
python main.py query "What is linear algebra?"

# → Answer with citations:
# Linear algebra studies vector spaces and linear mappings
# [Source: Cours___Algebre_lineaire.pdf]. It covers matrices,
# determinants, and diagonalisation [Source: Cours___Algebre_lineaire.pdf].
```

---

## Architecture

```
second-brain/
├── config/settings.py          ← Centralised configuration (.env)
├── main.py                     ← CLI (ingest, query, chat, stats...)
├── src/
│   ├── core/                   ← logging, errors, metrics
│   ├── ingestion/              ← Unified pipeline (CLI + API)
│   │   └── pipeline.py         ← parse → chunk → embed → store
│   ├── retrieval/              ← Reranker (MMR + LLM)
│   │   └── reranker.py
│   ├── evaluation/             ← RAG benchmark
│   │   └── benchmark.py        ← faithfulness, relevance, recall, latency
│   ├── ai/                     ← LLM client + RAG pipeline
│   │   ├── llm_client.py       ← Ollama HTTP wrapper
│   │   ├── rag_pipeline.py     ← RAG v4 (tracing, citations, injection detect)
│   │   └── tools.py            ← Tool registry (calculator, web_search...)
│   ├── agents_v2/              ← Minimalist 3-agent system
│   │   ├── planner.py          ← Decomposes request into steps
│   │   ├── retriever.py        ← Searches documents
│   │   └── executor.py         ← Executes and produces final answer
│   ├── agent/                  ← Full multi-agent system (advanced)
│   ├── memory/                 ← vector_store, history, conversation
│   ├── processing/             ← parsers, chunker, embedder
│   ├── data_layer/             ← document_manager (SQLite)
│   ├── tools/                  ← plugin system (registry, builtin, loader)
│   ├── api/main.py             ← FastAPI (auth, upload, metrics)
│   └── ui/                     ← Flask dashboard, Telegram bot
├── tests/
│   ├── test_core.py            ← 24 unit tests
│   ├── test_integration.py     ← 3 integration tests (Ollama required)
│   ├── test_agents.py          ← Multi-agent tests
│   └── test_tools.py           ← Tool system tests
├── benchmark_cases.json        ← 25 question/answer pairs for evaluation
├── pyproject.toml              ← Metadata + tool config (ruff, pytest, mypy)
├── requirements.txt            ← Locked dependencies
├── Dockerfile                  ← Multi-stage build
├── .env.example                ← Template without secrets
└── README.md                   ← This file
```

---

## Installation

### Prerequisites
- **Python 3.11+**
- **Ollama** installed and running (`ollama serve`)
- A pulled LLM model: `ollama pull qwen2.5:latest`

```bash
# 1. Clone
git clone <repo> && cd second-brain

# 2. Virtual environment
python -m venv .venv && source .venv/bin/activate

# 3. Dependencies
pip install -r requirements.txt

# 4. Configuration
cp .env.example .env
# Edit .env: set LLM_MODEL, optionally TELEGRAM_BOT_TOKEN, API_AUTH_TOKEN

# 5. Place your documents in data/raw/
#    (Supports PDF, DOCX, TXT, MD, XLSX, PPTX)

# 6. Ingest
python main.py ingest
```

---

## Usage

### CLI

| Command | Description |
|---------|-------------|
| `python main.py ingest` | Ingest all new documents |
| `python main.py ingest --file doc.pdf` | Ingest a specific file |
| `python main.py query "Question ?"` | Ask a question (RAG) |
| `python main.py chat` | Interactive chat |
| `python main.py list` | List ingested documents |
| `python main.py stats` | System statistics |
| `python main.py delete <id>` | Delete a document |
| `python main.py goals` | Manage goals |
| `python main.py tasks` | Manage tasks |

### API

```bash
# Run API (localhost only)
uvicorn src.api.main:app --host 127.0.0.1 --port 8000

# With auth token for network exposure
# In .env: API_AUTH_TOKEN=your_secret_token
# Then:
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
# → All /api/* routes require: Authorization: Bearer your_secret_token
```

**Endpoints:**

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | HTML dashboard |
| `POST` | `/api/chat` | RAG chat + tool-use |
| `POST` | `/api/documents/upload` | Upload + ingest |
| `GET` | `/api/documents` | Document list |
| `GET` | `/api/status` | System status (Ollama, tasks...) |
| `GET` | `/api/metrics` | Runtime metrics (latency, errors...) |
| `GET` | `/api/tasks` | Task kanban |

### Docker

```bash
docker build -t second-brain .
docker run -p 8000:8000 -v $(pwd)/data:/app/data second-brain
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **LLM** | Ollama (qwen2.5, qwen3, mistral...) |
| **Embeddings** | sentence-transformers (all-MiniLM-L6-v2, 384d) |
| **Vector DB** | ChromaDB (cosine similarity, persistent) |
| **Parsing** | PyMuPDF, python-docx, openpyxl, python-pptx |
| **API** | FastAPI + Pydantic v2 |
| **Dashboard** | Flask + vanilla JS (dark theme) |
| **Reranking** | MMR + LLM-based scoring |
| **Evaluation** | LLM-judged (faithfulness, relevance, correctness) |
| **Security** | Bearer auth, anti path-traversal, 50 MB upload limit, injection detection, deny-by-default |
| **Tests** | pytest (24 unit + 3 integration) |
| **CI/CD** | GitHub Actions (lint → test → docker build) |

---

## Agents

### Agents V2 (recommended — 3 agents)

```python
from src.agents_v2 import Planner, Retriever, Executor

planner = Planner(llm_client)
retriever = Retriever(rag_pipeline=rag)
executor = Executor(llm_client)

# Plan → Retrieve → Execute
steps = planner.plan("What is linear algebra?")
chunks = retriever.search(steps[0].params["query"])
result = executor.execute(steps, context=retriever.format_context(chunks))
print(result["answer"])
```

### Agents V1 (advanced — 19 modules)

Full multi-agent system in `src/agent/`: Coordinator, Strategic, Adaptive, Planner, Critic, Optimizer, Execution, BrainLoop, Attention...

---

## Evaluation

```bash
# Run the benchmark
python -c "
from src.ai.rag_pipeline import RAGPipeline
from src.evaluation import RAGBenchmark
bm = RAGBenchmark(RAGPipeline())
bm.load_cases('benchmark_cases.json')
report = bm.run()
print(bm.format_report(report))
bm.save_report(report, 'eval_report.json')
"
```

Metrics evaluated:
- **Faithfulness**: does the answer only use context ?
- **Relevance**: is the retrieved context relevant ?
- **Answer Correctness**: does the answer match ground truth ?
- **Chunk Recall**: how many expected sources were found ?
- **Latency**: total response time (ms)

---

## Security

- **API auth**: `Bearer <token>` required when binding `0.0.0.0`
- **Upload**: anti path-traversal (UUID), 50 MB limit, extension validation
- **Telegram**: deny-by-default (whitelist mandatory)
- **Injection**: 7 detection patterns (ignore all instructions, DAN, system prompt override...)
- **Calculator**: secure AST parser (no `eval`)
- **Secrets**: `.env` in `.gitignore`, `.env.example` without secrets

---

## Roadmap

- [x] Reliable V1 RAG (citations, tracing, injection detection)
- [x] 25-question benchmark
- [x] Unit + integration tests
- [x] Security (auth, upload, path traversal)
- [x] Simplified agents (3 agents)
- [x] CI/CD GitHub Actions
- [x] Docker
- [ ] Real-time monitoring dashboard
- [ ] Full offline mode (no HF Hub)
- [ ] Sandboxed plugins (Gmail, calendar, Spotify)

---

## License

MIT
