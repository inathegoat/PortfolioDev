# Second Brain

**Système RAG local, évalué, sécurisé et modulaire.**  
Indexe vos documents, répond avec citations exactes, détecte les injections.

[![CI](https://github.com/user/second-brain/actions/workflows/ci.yml/badge.svg)](https://github.com/user/second-brain/actions)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Démo rapide

```bash
# 1. Ingérer un document
python main.py ingest

# 2. Poser une question
python main.py query "Qu'est-ce que l'algèbre linéaire selon le cours ?"

# → Réponse avec citations :
# L'algèbre linéaire étudie les espaces vectoriels et les applications
# linéaires [Source: Cours___Algebre_lineaire.pdf]. Elle couvre les matrices,
# les déterminants et la diagonalisation [Source: Cours___Algebre_lineaire.pdf].
```

---

## Architecture

```
second-brain/
├── config/settings.py          ← Configuration centralisée (.env)
├── main.py                     ← CLI (ingest, query, chat, stats...)
├── src/
│   ├── core/                   ← logging, errors, metrics
│   ├── ingestion/              ← Pipeline unifié (CLI + API)
│   │   └── pipeline.py         ← parse → chunk → embed → store
│   ├── retrieval/              ← Reranker (MMR + LLM)
│   │   └── reranker.py
│   ├── evaluation/             ← Benchmark RAG
│   │   └── benchmark.py        ← faithfulness, relevance, recall, latency
│   ├── ai/                     ← LLM client + RAG pipeline
│   │   ├── llm_client.py       ← Ollama HTTP wrapper
│   │   ├── rag_pipeline.py     ← RAG v4 (tracing, citations, injection detect)
│   │   └── tools.py            ← Tool registry (calculator, web_search...)
│   ├── agents_v2/              ← Minimalist 3-agent system
│   │   ├── planner.py          ← Décompose la demande en étapes
│   │   ├── retriever.py        ← Cherche dans les documents
│   │   └── executor.py         ← Exécute et produit la réponse finale
│   ├── agent/                  ← Full multi-agent system (advanced)
│   ├── memory/                 ← vector_store, history, conversation
│   ├── processing/             ← parsers, chunker, embedder
│   ├── data_layer/             ← document_manager (SQLite)
│   ├── tools/                  ← plugin system (registry, builtin, loader)
│   ├── api/main.py             ← FastAPI (auth, upload, metrics)
│   └── ui/                     ← Flask dashboard, Telegram bot
├── tests/
│   ├── test_core.py            ← 24 tests unitaires
│   ├── test_integration.py     ← 3 tests d'intégration (Ollama requis)
│   ├── test_agents.py          ← Tests multi-agents
│   └── test_tools.py           ← Tests tool system
├── benchmark_cases.json        ← 25 questions/réponses pour évaluation
├── pyproject.toml              ← Metadata + tool config (ruff, pytest, mypy)
├── requirements.txt            ← Dépendances lockées
├── Dockerfile                  ← Build multi-stage
├── .env.example                ← Template sans secrets
└── README.md                   ← Ce fichier
```

---

## Installation

### Prérequis
- **Python 3.11+**
- **Ollama** installé et en cours d'exécution (`ollama serve`)
- Un modèle LLM pullé : `ollama pull qwen2.5:latest`

```bash
# 1. Cloner
git clone <repo> && cd second-brain

# 2. Environnement virtuel
python -m venv .venv && source .venv/bin/activate

# 3. Dépendances
pip install -r requirements.txt

# 4. Configuration
cp .env.example .env
# Éditer .env : choisir LLM_MODEL, optionnellement TELEGRAM_BOT_TOKEN, API_AUTH_TOKEN

# 5. Placer vos documents dans data/raw/
#    (PDF, DOCX, TXT, MD, XLSX, PPTX supportés)

# 6. Ingérer
python main.py ingest
```

---

## Utilisation

### CLI

| Commande | Description |
|----------|-------------|
| `python main.py ingest` | Ingérer tous les nouveaux documents |
| `python main.py ingest --file doc.pdf` | Ingérer un fichier spécifique |
| `python main.py query "Question ?"` | Poser une question (RAG) |
| `python main.py chat` | Chat interactif |
| `python main.py list` | Lister les documents ingérés |
| `python main.py stats` | Statistiques système |
| `python main.py delete <id>` | Supprimer un document |
| `python main.py goals` | Gérer les objectifs |
| `python main.py tasks` | Gérer les tâches |

### API

```bash
# Lancer l'API (localhost uniquement)
uvicorn src.api.main:app --host 127.0.0.1 --port 8000

# Avec auth token pour exposition réseau
# Dans .env : API_AUTH_TOKEN=votre_token_secret
# Puis :
uvicorn src.api.main:app --host 0.0.0.0 --port 8000
# → Toutes les routes /api/* nécessitent : Authorization: Bearer votre_token_secret
```

**Endpoints :**

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/` | Dashboard HTML |
| `POST` | `/api/chat` | Chat RAG + tool-use |
| `POST` | `/api/documents/upload` | Upload + ingestion |
| `GET` | `/api/documents` | Liste des documents |
| `GET` | `/api/status` | État système (Ollama, tâches...) |
| `GET` | `/api/metrics` | Métriques runtime (latence, erreurs...) |
| `GET` | `/api/tasks` | Kanban des tâches |

### Docker

```bash
docker build -t second-brain .
docker run -p 8000:8000 -v $(pwd)/data:/app/data second-brain
```

---

## Stack technique

| Couche | Technologie |
|--------|-------------|
| **LLM** | Ollama (qwen2.5, qwen3, mistral...) |
| **Embeddings** | sentence-transformers (all-MiniLM-L6-v2, 384d) |
| **Vector DB** | ChromaDB (cosine similarity, persistent) |
| **Parsing** | PyMuPDF, python-docx, openpyxl, python-pptx |
| **API** | FastAPI + Pydantic v2 |
| **Dashboard** | Flask + vanilla JS (dark theme) |
| **Reranking** | MMR + LLM-based scoring |
| **Évaluation** | LLM-judged (faithfulness, relevance, correctness) |
| **Sécurité** | Bearer auth, anti path-traversal, injection detection, deny-by-default |
| **Tests** | pytest (24 unit + 3 integration) |
| **CI/CD** | GitHub Actions (lint → test → docker build) |

---

## Agents

### Agents V2 (recommandé — 3 agents)

```python
from src.agents_v2 import Planner, Retriever, Executor

planner = Planner(llm_client)
retriever = Retriever(rag_pipeline=rag)
executor = Executor(llm_client)

# Plan → Retrieve → Execute
steps = planner.plan("Qu'est-ce que l'algèbre linéaire ?")
chunks = retriever.search(steps[0].params["query"])
result = executor.execute(steps, context=retriever.format_context(chunks))
print(result["answer"])
```

### Agents V1 (avancé — 19 modules)

Système multi-agent complet dans `src/agent/` : Coordinator, Strategic, Adaptive, Planner, Critic, Optimizer, Execution, BrainLoop, Attention...

---

## Évaluation

```bash
# Lancer le benchmark
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

Métriques évaluées :
- **Faithfulness** : l'answer utilise-t-elle uniquement le contexte ?
- **Relevance** : le contexte récupéré est-il pertinent ?
- **Answer Correctness** : la réponse correspond-elle à la vérité terrain ?
- **Chunk Recall** : combien de sources attendues ont été retrouvées ?
- **Latence** : temps de réponse total (ms)

---

## Sécurité

- **Auth API** : `Bearer <token>` obligatoire si bind `0.0.0.0`
- **Upload** : anti path-traversal (UUID), limite 50 MB, validation extensions
- **Telegram** : deny-by-default (liste blanche obligatoire)
- **Injection** : 7 patterns de détection (ignore all instructions, DAN, system prompt override...)
- **Calculator** : parseur AST sécurisé (pas de `eval`)
- **Secrets** : `.env` dans `.gitignore`, `.env.example` sans secrets

---

## Roadmap

- [x] V1 RAG fiable (citations, tracing, injection detection)
- [x] Benchmark 25 questions
- [x] Tests unitaires + intégration
- [x] Sécurité (auth, upload, path traversal)
- [x] Agents simplifiés (3 agents)
- [x] CI/CD GitHub Actions
- [x] Docker
- [ ] Dashboard monitoring temps réel
- [ ] Mode hors-ligne complet (pas de HF Hub)
- [ ] Plugins sandboxés (Gmail, calendrier, Spotify)

---

## Licence

MIT
