"""
Second Brain — FastAPI Dashboard (src/api/main.py)
===================================================
API REST + Dashboard web pour le Second Brain.

Lancement :
  uvicorn src.api.main:app --host 127.0.0.1 --port 8000
"""

import logging
import os
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

app = FastAPI(title="Second Brain API", version="2.1")

# ── Constants (from settings) ────────────────────────────────────────

from config.settings import (
    RAW_DIR, NOTES_DIR, DB_DIR, TASKS_DB, CONV_DB,
    ALLOWED_EXTENSIONS, API_AUTH_TOKEN, API_HOST,
)

RAW_DATA_DIR = RAW_DIR
for d in [RAW_DIR, NOTES_DIR, DB_DIR]:
    d.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB

# ── Auth Middleware ───────────────────────────────────────────────────

if API_AUTH_TOKEN:
    logger.info("API auth enabled — token required")
else:
    logger.warning("API running without auth — do NOT expose to network")


@app.on_event("startup")
async def security_check():
    if API_HOST in ("0.0.0.0", "::") and not API_AUTH_TOKEN:
        logger.critical(
            "REFUSING TO START: API_HOST=%s without API_AUTH_TOKEN. "
            "Set API_AUTH_TOKEN in .env to expose the API to the network, "
            "or set API_HOST=127.0.0.1 for local-only access.",
            API_HOST,
        )
        import sys
        sys.exit(1)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Allow dashboard and static files without auth
    if path == "/" or path.startswith("/static") or path.startswith("/favicon"):
        return await call_next(request)
    # API routes require auth if token is set
    if API_AUTH_TOKEN and path.startswith("/api/"):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or auth[7:] != API_AUTH_TOKEN:
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized. Provide a valid Bearer token."},
            )
    return await call_next(request)

# ── Lazy imports ────────────────────────────────────────────────────

def _get_llm():
    from src.ai.llm_client import LLMClient
    return LLMClient()

def _get_memory():
    from src.memory.conversation import ConversationMemory
    return ConversationMemory(db_path=CONV_DB)

def _get_tools():
    from src.ai.tools import get_tools_schema, parse_and_execute_tools
    return get_tools_schema, parse_and_execute_tools

# ── Singletons ──────────────────────────────────────────────────────

_memory = None
_jarvis = None

@app.on_event("startup")
async def startup():
    global _memory, _jarvis
    try:
        _memory = _get_memory()
    except Exception as e:
        logger.warning(f"Memory init failed (API will work without memory): {e}")
        _memory = None

    try:
        from src.agent.jarvis import JarvisAgent
        llm = _get_llm()
        _jarvis = JarvisAgent(
            llm_client=llm, vector_store=None,
            memory=_memory, interval_minutes=15,
        )
        _jarvis.start()
        logger.info("Jarvis started in background")
    except Exception as e:
        logger.warning(f"Jarvis could not start (API still functional): {e}")
        _jarvis = None

@app.on_event("shutdown")
async def shutdown():
    if _jarvis:
        _jarvis.stop()

# ── Schémas Pydantic ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="User message")
    session_id: str = Field(default="default", max_length=64)
    use_rag: bool = True
    use_web: bool = False
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    mode: str = Field(default="agent", pattern=r"^(simple|agent)$")  # agent = autonomous, simple = RAG only

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message cannot be empty")
        return v.strip()

class ChatResponse(BaseModel):
    response: str
    session_id: str
    tool_calls: list = []
    sources: list = []
    duration_ms: Optional[int] = None
    confidence: str = "medium"
    plan: list = []
    actions: list = []
    mode: str = "simple"

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="", max_length=5000)
    objective: str = Field(default="", max_length=500)
    priority: int = Field(default=3, ge=1, le=10)

class TaskUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(todo|in_progress|done)$")

class GoalCreate(BaseModel):
    goal_id: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    priority: int = Field(default=5, ge=1, le=10)
    keywords: list[str] = Field(default_factory=list)

# ── Routes : Chat ────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    import time
    start = time.time()
    llm = _get_llm()
    if not llm.is_available():
        raise HTTPException(503, detail="LLM is not available. Check Ollama or API key.")

    # ── Agent mode: autonomous planning + retrieval + execution ──────
    if req.mode == "agent":
        try:
            from src.agents_v2 import Coordinator, BriefingGenerator
            from src.ai.rag_pipeline import RAGPipeline
            from src.core.permissions import PermissionManager

            rag = RAGPipeline(llm_client=llm, use_reranker=True, use_hybrid_search=True)
            coord = Coordinator(
                llm_client=llm,
                rag_pipeline=rag,
                permission_manager=PermissionManager(),
            )
            result = coord.handle(req.message)

            # Save to memory
            if hasattr(_memory, "add_message"):
                _memory.add_message("user", req.message, req.session_id)
                _memory.add_message("assistant", result.answer, req.session_id)

            duration = int((time.time() - start) * 1000)
            return ChatResponse(
                response=result.answer,
                session_id=req.session_id,
                sources=[
                    {"source_file": s.get("source_file", ""), "relevance": s.get("relevance", 0),
                     "preview": s.get("preview", "")[:200]}
                    for s in result.sources
                ],
                confidence=result.confidence,
                plan=result.plan,
                actions=[a for a in result.actions_approved],
                duration_ms=duration,
                mode="agent",
            )
        except Exception as e:
            logger.error(f"Agent mode failed, falling back to simple: {e}")

    # ── Simple mode: RAG + tool-use ──────────────────────────────────
    get_tools_schema, parse_and_execute_tools = _get_tools()

    if hasattr(_memory, "get_ollama_messages"):
        history = _memory.get_ollama_messages(req.session_id)
    else:
        raw_hist = _memory.get_history(req.session_id) if _memory else []
        history = [{"role": m["role"], "content": m["content"]} for m in raw_hist]

    system = (
        "You are Second Brain, a personal AI assistant. "
        "Answer in the same language as the user. "
        "Be concise and factual.\n\n"
        + get_tools_schema()
    )

    sources = []
    if req.use_rag:
        try:
            from src.memory.vector_store import VectorStore
            chunks = VectorStore().search(req.message, k=4)
            if chunks:
                ctx = "\n\n".join(
                    c.get("text", str(c)) for c in chunks if isinstance(c, dict)
                )
                system += f"\n\nContext from your documents:\n{ctx}"
                sources = [c.get("source","") for c in chunks if isinstance(c, dict)]
        except Exception as e:
            logger.debug(f"RAG unavailable: {e}")

    if req.use_web:
        try:
            from src.ai.tools import web_search
            wr = web_search(req.message, max_results=3)
            if wr.get("results"):
                wctx = "\n".join(f"- {r['title']}: {r['url']}" for r in wr["results"])
                system += f"\n\nWeb results:\n{wctx}"
        except Exception as e:
            logger.debug(f"Web search failed: {e}")

    messages = history + [{"role": "user", "content": req.message}]
    raw_response = llm.chat(messages=messages, system_prompt=system, temperature=req.temperature)
    clean_response, tool_results = parse_and_execute_tools(raw_response)

    if _memory and hasattr(_memory, "add_message"):
        _memory.add_message("user", req.message, req.session_id)
        _memory.add_message("assistant", clean_response, req.session_id)

    duration = int((time.time() - start) * 1000)
    return ChatResponse(
        response=clean_response,
        session_id=req.session_id,
        tool_calls=tool_results,
        sources=[s for s in sources if s],
        duration_ms=duration,
        mode="simple",
    )

# ── Routes : Documents ───────────────────────────────────────────────

@app.post("/api/documents/upload")
async def upload_document(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, detail="No filename provided")

    # Anti path traversal: only keep the basename, strip directory components
    safe_name = Path(file.filename).name
    if not safe_name or safe_name.startswith("."):
        raise HTTPException(400, detail="Invalid filename")

    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, detail=f"Format non supporté: {suffix} (autorisés: {sorted(ALLOWED_EXTENSIONS)})")

    # Generate unique filename to prevent collisions and path injection
    unique_name = f"{uuid.uuid4().hex[:12]}_{safe_name}"
    dest = RAW_DIR / unique_name

    # Save with size limit
    size = 0
    with open(dest, "wb") as f:
        while chunk := file.file.read(8192):
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, detail=f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024} MB)")
            f.write(chunk)

    background_tasks.add_task(_ingest_document, dest)
    return {"status": "uploading", "filename": safe_name, "stored_as": unique_name}

@app.get("/api/documents")
async def list_documents():
    files = []
    if RAW_DIR.exists():
        files = [
            {"name": f.name, "size_kb": round(f.stat().st_size/1024,1),
             "type": f.suffix.lstrip(".").upper(),
             "uploaded_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat()}
            for f in sorted(RAW_DIR.iterdir(), key=lambda x: -x.stat().st_mtime)
            if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
        ]
    return {"documents": files, "count": len(files)}

@app.delete("/api/documents/{filename}")
async def delete_document(filename: str):
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        raise HTTPException(400, detail="Invalid filename")
    path = RAW_DIR / safe_name
    if not path.exists() or not path.is_file():
        raise HTTPException(404, detail=f"Document introuvable: {filename}")
    path.unlink()
    return {"status": "deleted", "filename": safe_name}

def _ingest_document(path: Path):
    """Full ingestion pipeline: parse → chunk → embed → store."""
    try:
        from src.ingestion.pipeline import IngestionPipeline
        pipeline = IngestionPipeline()
        result = pipeline.ingest_file(path)
        logger.info(
            f"Ingested {path.name}: {result.chunks_count} chunks → {result.status}"
        )
    except Exception as e:
        logger.error(f"Ingestion failed for {path.name}: {e}")

# ── Routes : Tâches ──────────────────────────────────────────────────

def _init_tasks_db():
    with sqlite3.connect(TASKS_DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT DEFAULT '',
                objective   TEXT DEFAULT '',
                status      TEXT DEFAULT 'todo',
                priority    INTEGER DEFAULT 3,
                created_at  TEXT NOT NULL,
                updated_at  TEXT
            )
        """)
        conn.commit()

_init_tasks_db()

@app.get("/api/tasks")
async def get_tasks(status: Optional[str] = None):
    q = "SELECT id,title,description,objective,status,priority,created_at,updated_at FROM tasks"
    params = []
    if status:
        q += " WHERE status = ?"; params.append(status)
    q += " ORDER BY priority DESC, id DESC"
    with sqlite3.connect(TASKS_DB) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(q, params).fetchall()
    tasks = [dict(r) for r in rows]
    kanban = {
        "todo":        [t for t in tasks if t["status"]=="todo"],
        "in_progress": [t for t in tasks if t["status"]=="in_progress"],
        "done":        [t for t in tasks if t["status"]=="done"],
    }
    return {"tasks": tasks, "kanban": kanban, "count": len(tasks)}

@app.post("/api/tasks", status_code=201)
async def create_task_endpoint(task: TaskCreate):
    with sqlite3.connect(TASKS_DB) as conn:
        cur = conn.execute(
            "INSERT INTO tasks (title,description,objective,priority,created_at) VALUES (?,?,?,?,?)",
            (task.title, task.description, task.objective, task.priority, datetime.now().isoformat()),
        )
        conn.commit()
    return {"status": "created", "id": cur.lastrowid, "title": task.title}

@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, update: TaskUpdate):
    valid = {"todo", "in_progress", "done"}
    if update.status not in valid:
        raise HTTPException(400, detail=f"Statut invalide. Valeurs: {valid}")
    with sqlite3.connect(TASKS_DB) as conn:
        n = conn.execute(
            "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
            (update.status, datetime.now().isoformat(), task_id),
        ).rowcount
        conn.commit()
    if n == 0:
        raise HTTPException(404, detail=f"Tâche #{task_id} introuvable")
    return {"status": "updated", "task_id": task_id, "new_status": update.status}

@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int):
    with sqlite3.connect(TASKS_DB) as conn:
        n = conn.execute("DELETE FROM tasks WHERE id=?", (task_id,)).rowcount
        conn.commit()
    if n == 0:
        raise HTTPException(404, detail=f"Tâche #{task_id} introuvable")
    return {"status": "deleted", "task_id": task_id}

# ── Routes : Objectifs ───────────────────────────────────────────────

@app.get("/api/goals")
async def get_goals():
    try:
        from src.goals import load_goals
        return {"goals": load_goals()}
    except Exception as e:
        return {"goals": [], "error": str(e)}

# ── Routes : Insights ────────────────────────────────────────────────

@app.get("/api/insights")
async def get_insights(limit: int = 20):
    if not _jarvis:
        return {"insights": [], "count": 0}
    ins = _jarvis.insights[-limit:][::-1]
    return {"insights": ins, "count": len(_jarvis.insights)}

# ── Routes : Jarvis ──────────────────────────────────────────────────

@app.get("/api/jarvis/status")
async def jarvis_status():
    if not _jarvis:
        return {"running": False, "error": "Jarvis non initialisé"}
    return _jarvis.get_status()

@app.post("/api/jarvis/toggle")
async def jarvis_toggle():
    if not _jarvis:
        raise HTTPException(503, detail="Jarvis non initialisé")
    if _jarvis.is_running:
        _jarvis.stop()
    else:
        _jarvis.start()
    return {"running": _jarvis.is_running}

@app.post("/api/jarvis/run-now")
async def jarvis_run_now(background_tasks: BackgroundTasks):
    if not _jarvis:
        raise HTTPException(503, detail="Jarvis non initialisé")
    background_tasks.add_task(_jarvis._run_cycle)
    return {"status": "cycle_triggered"}

# ── Routes : Système ─────────────────────────────────────────────────

@app.get("/api/metrics")
async def get_metrics():
    """Return runtime metrics (latency, errors, recall, qps)."""
    try:
        from src.core.metrics import get_collector
        collector = get_collector()
        return collector.summary()
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/status")
async def system_status():
    from src.ai.tools import TOOL_REGISTRY
    llm = _get_llm()
    doc_count = len(list(RAW_DIR.glob("*"))) if RAW_DIR.exists() else 0
    task_stats = {"todo": 0, "in_progress": 0, "done": 0}
    try:
        with sqlite3.connect(TASKS_DB) as conn:
            for row in conn.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status").fetchall():
                task_stats[row[0]] = row[1]
    except Exception:
        pass
    return {
        "ollama": {"running": llm.is_available(), "model": llm.model, "available_models": llm.list_models()},
        "jarvis": _jarvis.get_status() if _jarvis else {"running": False},
        "documents": {"count": doc_count},
        "tasks": task_stats,
        "tools": list(TOOL_REGISTRY.keys()),
        "timestamp": datetime.now().isoformat(),
    }

# ── Routes : Study Mode ─────────────────────────────────────────────

@app.post("/api/study/quiz")
async def generate_quiz(topic: str, num: int = 5, qtype: str = "qcm"):
    """Generate quiz from documents."""
    try:
        from src.modes.study import StudyMode
        from src.ai.rag_pipeline import RAGPipeline
        llm = _get_llm()
        rag = RAGPipeline(llm_client=llm, use_reranker=False)
        mode = StudyMode(llm_client=llm, rag_pipeline=rag)
        questions = mode.generate_quiz(topic, num, qtype)
        return {"topic": topic, "questions": [
            {"q": q.question, "options": q.options, "correct": q.correct_index,
             "explanation": q.explanation, "source": q.source}
            for q in questions
        ]}
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.post("/api/study/flashcards")
async def generate_flashcards(topic: str, num: int = 10):
    """Generate flashcards from documents."""
    try:
        from src.modes.study import StudyMode
        from src.ai.rag_pipeline import RAGPipeline
        llm = _get_llm()
        rag = RAGPipeline(llm_client=llm, use_reranker=False)
        mode = StudyMode(llm_client=llm, rag_pipeline=rag)
        cards = mode.generate_flashcards(topic, num)
        return {"topic": topic, "flashcards": [
            {"front": c.front, "back": c.back, "source": c.source}
            for c in cards
        ]}
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.post("/api/study/plan")
async def generate_study_plan(subject: str, hours: float = 10, days: int = 7):
    """Generate a study plan."""
    try:
        from src.modes.study import StudyMode
        from src.ai.rag_pipeline import RAGPipeline
        llm = _get_llm()
        rag = RAGPipeline(llm_client=llm, use_reranker=False)
        mode = StudyMode(llm_client=llm, rag_pipeline=rag)
        plan = mode.generate_study_plan(subject, hours, days)
        return {
            "title": plan.title,
            "total_hours": plan.total_duration_hours,
            "sources": plan.sources,
            "sessions": plan.sessions,
        }
    except Exception as e:
        raise HTTPException(500, detail=str(e))


# ── Routes : Finance Mode ───────────────────────────────────────────

_app_finance = None  # lazy singleton


def _get_finance():
    global _app_finance
    if _app_finance is None:
        from src.modes.finance import FinanceMode
        from src.ai.rag_pipeline import RAGPipeline
        llm = _get_llm()
        rag = RAGPipeline(llm_client=llm, use_reranker=False)
        _app_finance = FinanceMode(llm_client=llm, rag_pipeline=rag)
    return _app_finance


@app.get("/api/finance/report")
async def analyze_report(document: str):
    """Analyze a financial report."""
    fm = _get_finance()
    metrics = fm.analyze_report(document)
    summary = fm.summarize_report(document)
    return {"document": document, "metrics": {
        "revenue": metrics.revenue,
        "profit": metrics.profit,
        "margin_pct": metrics.margin,
        "debt_ratio": metrics.debt_ratio,
        "growth_pct": metrics.growth_rate,
    }, "summary": summary}


@app.post("/api/finance/portfolio/position")
async def add_portfolio_position(
    ticker: str, name: str = "", shares: float = 0,
    cost: float = 0, sector: str = "",
    alert_below: Optional[float] = None, alert_above: Optional[float] = None,
):
    """Add a position to the portfolio."""
    fm = _get_finance()
    fm.add_position(ticker, name, shares, cost, sector, alert_below, alert_above)
    return {"status": "added", "ticker": ticker}


@app.post("/api/finance/portfolio/price")
async def update_portfolio_price(ticker: str, price: float):
    """Update a position's price."""
    fm = _get_finance()
    fm.update_price(ticker, price)
    return {"status": "updated", "ticker": ticker, "price": price}


@app.get("/api/finance/portfolio")
async def get_portfolio():
    """Get portfolio summary."""
    fm = _get_finance()
    summary = fm.get_portfolio_summary()
    return {
        "total_value": summary.total_value,
        "total_cost": summary.total_cost,
        "gain_loss": summary.total_gain_loss,
        "gain_loss_pct": summary.total_gain_loss_pct,
        "positions": [
            {"ticker": p.ticker, "name": p.name, "shares": p.shares,
             "avg_cost": p.avg_cost, "current_price": p.current_price,
             "value": round(p.shares * p.current_price, 2),
             "gain_pct": round((p.current_price - p.avg_cost) / p.avg_cost * 100, 2) if p.avg_cost else 0}
            for p in summary.positions
        ],
        "alerts": summary.alerts,
    }


# ── Routes : LLM Providers ──────────────────────────────────────────

@app.get("/api/llm/providers")
async def list_llm_providers():
    """List available LLM providers."""
    try:
        from src.ai.llm_providers import MultiLLMClient
        client = MultiLLMClient()
        providers = []
        for name, cfg in client._providers.items():
            providers.append({
                "name": name,
                "model": cfg.model,
                "is_local": cfg.is_local,
                "available": client.is_available(name),
                "has_key": bool(cfg.api_key),
            })
        return {"providers": providers, "default": "ollama"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/llm/providers")
async def add_llm_provider(
    name: str, api_key: str = "", model: str = "",
    base_url: str = "", max_tokens: int = 2048,
):
    """Add or update an LLM provider."""
    try:
        from src.ai.llm_providers import MultiLLMClient
        client = MultiLLMClient()
        kwargs = {"max_tokens": max_tokens}
        if api_key:
            kwargs["api_key"] = api_key
        if model:
            kwargs["model"] = model
        if base_url:
            kwargs["base_url"] = base_url
        client.add_provider(name, **kwargs)
        return {"status": "added", "name": name, "model": client._providers[name].model}
    except Exception as e:
        raise HTTPException(500, detail=str(e))


@app.delete("/api/llm/providers/{name}")
async def remove_llm_provider(name: str):
    """Remove an LLM provider (except ollama)."""
    if name == "ollama":
        raise HTTPException(400, detail="Cannot remove ollama (local provider)")
    try:
        from src.ai.llm_providers import MultiLLMClient
        client = MultiLLMClient()
        client.remove_provider(name)
        return {"status": "removed", "name": name}
    except Exception as e:
        raise HTTPException(500, detail=str(e))

# ── Dashboard HTML ───────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(content=DASHBOARD_HTML)

DASHBOARD_HTML = (
    "<!DOCTYPE html>"
    "<html lang='fr'>"
    "<head>"
    "<meta charset='UTF-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
    "<title>Second Brain</title>"
    "<link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css'>"
    "<script src='https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js'></script>"
    "<style>"
    ":root{--bg:#0f0f0f;--surface:#1a1a1a;--surface2:#242424;--border:rgba(255,255,255,0.08);--text:#e8e8e8;--muted:#888;--accent:#4f98a3;--accent2:#2d7a85;--danger:#e05c5c;--success:#6daa45;--radius:12px;}"
    "*{box-sizing:border-box;margin:0;padding:0}"
    "body{background:var(--bg);color:var(--text);font-family:'Inter',system-ui,sans-serif;font-size:14px;min-height:100vh}"
    "header{background:var(--surface);border-bottom:1px solid var(--border);padding:14px 24px;display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:100}"
    "header h1{font-size:16px;font-weight:600}"
    ".badge{background:var(--accent);color:#fff;border-radius:999px;padding:2px 10px;font-size:11px}"
    ".badge.off{background:var(--danger)}"
    "nav{display:flex;gap:4px;margin-left:auto}"
    "nav button{background:none;border:1px solid var(--border);color:var(--muted);border-radius:8px;padding:6px 14px;cursor:pointer;font-size:13px;transition:all .15s}"
    "nav button:hover,nav button.active{background:var(--surface2);color:var(--text);border-color:var(--accent)}"
    "main{max-width:1100px;margin:0 auto;padding:24px 16px}"
    ".tab{display:none}.tab.active{display:block}"
    ".card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;margin-bottom:16px}"
    ".card h3{font-size:12px;color:var(--muted);margin-bottom:12px;text-transform:uppercase;letter-spacing:.05em}"
    ".stats{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}"
    ".stat{background:var(--surface2);border-radius:10px;padding:16px;text-align:center}"
    ".stat-val{font-size:28px;font-weight:700;color:var(--accent)}"
    ".stat-lbl{font-size:11px;color:var(--muted);margin-top:4px}"
    ".chat-box{height:400px;overflow-y:auto;background:var(--surface2);border-radius:10px;padding:16px;margin-bottom:12px;display:flex;flex-direction:column;gap:10px}"
    ".msg{max-width:80%;padding:10px 14px;border-radius:10px;line-height:1.5;font-size:13px}"
    ".msg.user{background:var(--accent2);align-self:flex-end}"
    ".msg.assistant{background:var(--surface);border:1px solid var(--border);align-self:flex-start}"
    ".msg.system{background:transparent;border:1px dashed var(--border);color:var(--muted);font-size:12px;align-self:center}"
    ".chat-input{display:flex;gap:8px}"
    ".chat-input input{flex:1;background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:10px 14px;color:var(--text);font-size:14px;outline:none}"
    ".chat-input input:focus{border-color:var(--accent)}"
    ".chat-input button{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:10px 20px;cursor:pointer;font-weight:600}"
    ".toggles{display:flex;gap:8px;margin-bottom:10px}"
    ".toggle-btn{background:var(--surface2);border:1px solid var(--border);color:var(--muted);border-radius:6px;padding:4px 12px;cursor:pointer;font-size:12px}"
    ".toggle-btn.on{border-color:var(--accent);color:var(--accent);background:rgba(79,152,163,.1)}"
    ".kanban{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}"
    ".col-title{font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px}"
    ".col-todo .col-title{color:var(--muted)}.col-in_progress .col-title{color:#e8a23a}.col-done .col-title{color:var(--success)}"
    ".task-card{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:8px}"
    ".task-title{font-size:13px;font-weight:500}"
    ".task-meta{font-size:11px;color:var(--muted);margin-top:4px}"
    ".task-actions{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}"
    ".task-actions button{background:none;border:1px solid var(--border);color:var(--muted);border-radius:5px;padding:2px 8px;font-size:11px;cursor:pointer}"
    ".task-actions button:hover{border-color:var(--accent);color:var(--accent)}"
    ".doc-item{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border)}"
    ".doc-icon{background:var(--surface2);border-radius:6px;padding:6px 10px;font-size:11px;font-weight:700;color:var(--accent);min-width:44px;text-align:center}"
    ".doc-name{font-size:13px;flex:1}"
    ".doc-size{font-size:11px;color:var(--muted)}"
    ".doc-delete{background:none;border:none;color:var(--muted);cursor:pointer;font-size:16px}"
    ".doc-delete:hover{color:var(--danger)}"
    ".upload-zone{border:2px dashed var(--border);border-radius:10px;padding:32px;text-align:center;color:var(--muted);cursor:pointer;transition:border-color .2s}"
    ".upload-zone:hover{border-color:var(--accent);color:var(--text)}"
    ".insight-item{padding:10px 0;border-bottom:1px solid var(--border);font-size:13px}"
    ".insight-time{font-size:11px;color:var(--muted)}"
    ".jarvis-status{display:flex;align-items:center;gap:10px}"
    ".dot{width:8px;height:8px;border-radius:50%;background:var(--danger)}"
    ".dot.on{background:var(--success);animation:pulse 2s infinite}"
    "@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}"
    ".btn-primary{background:var(--accent);color:#fff;border:none;border-radius:8px;padding:8px 18px;cursor:pointer;font-weight:600}"
    ".btn-primary:hover{background:var(--accent2)}"
    ".form-input{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:8px 12px;color:var(--text);font-size:13px;width:100%;outline:none}"
    ".form-input:focus{border-color:var(--accent)}"
    ".form-row{margin-bottom:10px}"
    ".form-row label{display:block;font-size:12px;color:var(--muted);margin-bottom:4px}"
    ".spinner{display:inline-block;width:14px;height:14px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .6s linear infinite}"
    "@keyframes spin{to{transform:rotate(360deg)}}"
    "@media(max-width:700px){.kanban{grid-template-columns:1fr}.stats{grid-template-columns:1fr 1fr}}"
    "</style></head><body>"
    "<header>"
    "<svg width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='var(--accent)' stroke-width='2'>"
    "<circle cx='12' cy='12' r='9'/><path d='M12 7v5l3 3'/>"
    "</svg>"
    "<h1>Second Brain</h1>"
    "<span id='ollamaStatus' class='badge off'>Ollama</span>"
    "<nav>"
    "<button class='active' onclick='switchTab(\"overview\")'>Vue d'ensemble</button>"
    "<button onclick='switchTab(\"chat\")'>Chat</button>"
    "<button onclick='switchTab(\"tasks\")'>T\u00e2ches</button>"
    "<button onclick='switchTab(\"docs\")'>Documents</button>"
    "<button onclick='switchTab(\"jarvis\")'>Jarvis</button>"
    "</nav></header>"
    "<main>"
    "<div id='tab-overview' class='tab active'>"
    "<div class='card'><h3>\u00c9tat du syst\u00e8me</h3>"
    "<div class='stats'>"
    "<div class='stat'><div class='stat-val' id='statDocs'>&#8212;</div><div class='stat-lbl'>Documents</div></div>"
    "<div class='stat'><div class='stat-val' id='statTodo'>&#8212;</div><div class='stat-lbl'>&Agrave; faire</div></div>"
    "<div class='stat'><div class='stat-val' id='statProg'>&#8212;</div><div class='stat-lbl'>En cours</div></div>"
    "<div class='stat'><div class='stat-val' id='statDone'>&#8212;</div><div class='stat-lbl'>Termin&eacute;es</div></div>"
    "<div class='stat'><div class='stat-val' id='statIns'>&#8212;</div><div class='stat-lbl'>Insights</div></div>"
    "<div class='stat'><div class='stat-val' id='statMdl' style='font-size:13px'>&#8212;</div><div class='stat-lbl'>Mod\u00e8le</div></div>"
    "</div></div>"
    "<div class='card'><h3>Derniers insights Jarvis</h3>"
    "<div id='recentIns'><span style='color:var(--muted);font-size:13px'>Aucun insight.</span></div>"
    "</div></div>"
    "<div id='tab-chat' class='tab'>"
    "<div class='card'>"
    "<div class='toggles'>"
    "<button class='toggle-btn on' id='tRag' onclick='toggleOpt(\"rag\")'>&#128269; RAG</button>"
    "<button class='toggle-btn' id='tWeb' onclick='toggleOpt(\"web\")'>&#127760; Internet</button>"
    "</div>"
    "<div class='chat-box' id='chatBox'>"
    "<div class='msg system'>Session d\u00e9marr\u00e9e. Posez votre question.</div>"
    "</div>"
    "<div class='chat-input'>"
    "<input type='text' id='chatInput' placeholder='Posez votre question...' onkeydown='if(event.key===\"Enter\")sendChat()'>"
    "<button onclick='sendChat()'>Envoyer</button>"
    "</div></div></div>"
    "<div id='tab-tasks' class='tab'>"
    "<div class='card' style='margin-bottom:16px'>"
    "<h3>Nouvelle t\u00e2che</h3>"
    "<div class='form-row'><label>Titre *</label><input class='form-input' id='ntTitle' placeholder='Titre'></div>"
    "<div class='form-row'><label>Description</label><input class='form-input' id='ntDesc' placeholder='Description optionnelle'></div>"
    "<div class='form-row'><label>Objectif li\u00e9</label><input class='form-input' id='ntObj' placeholder='ex: Apprendre le ML'></div>"
    "<button class='btn-primary' onclick='createTask()' style='margin-top:4px'>+ Cr\u00e9er</button>"
    "</div>"
    "<div class='kanban' id='kanban'>"
    "<div class='col-todo'><div class='col-title'>&Agrave; faire</div><div id='col-todo'></div></div>"
    "<div class='col-in_progress'><div class='col-title'>En cours</div><div id='col-in_progress'></div></div>"
    "<div class='col-done'><div class='col-title'>Termin\u00e9es</div><div id='col-done'></div></div>"
    "</div></div>"
    "<div id='tab-docs' class='tab'>"
    "<div class='card' style='margin-bottom:16px'><h3>Ajouter des documents</h3>"
    "<div class='upload-zone' id='upZone' onclick='document.getElementById(\"fi\").click()'>"
    "Cliquez ou glissez vos fichiers ici<br><span style='font-size:11px'>PDF, Word, Excel, PowerPoint, TXT, Markdown</span>"
    "</div>"
    "<input type='file' id='fi' style='display:none' accept='.pdf,.txt,.md,.docx,.xlsx,.pptx' multiple onchange='uploadFiles(this.files)'>"
    "</div>"
    "<div class='card'><h3>Documents ing\u00e9r\u00e9s</h3>"
    "<div id='docList'><span style='color:var(--muted)'>Chargement...</span></div>"
    "</div></div>"
    "<div id='tab-jarvis' class='tab'>"
    "<div class='card'><h3>Agent Jarvis</h3>"
    "<div class='jarvis-status'>"
    "<div class='dot' id='jDot'></div>"
    "<span id='jState' style='font-size:13px'>&#8212;</span>"
    "<button class='btn-primary' id='jToggle' onclick='toggleJarvis()' style='margin-left:auto'>&#8212;</button>"
    "<button class='btn-primary' onclick='runNow()' style='background:var(--surface2);border:1px solid var(--border);color:var(--text)'>Lancer maintenant</button>"
    "</div>"
    "<div style='margin-top:14px;font-size:12px;color:var(--muted)' id='jLastRun'></div>"
    "</div>"
    "<div class='card'><h3>Tous les insights</h3>"
    "<div id='allIns'><span style='color:var(--muted);font-size:13px'>Aucun insight.</span></div>"
    "</div></div>"
    "</main>"
    "<script>"
    "const api=(p,o={})=>fetch(p,{headers:{'Content-Type':'application/json'},...o}).then(r=>r.json());"
    "const sid='s_'+Date.now();"
    "let useRag=true,useWeb=false;"
    "function switchTab(n){document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.querySelectorAll('nav button').forEach(b=>b.classList.remove('active'));document.getElementById('tab-'+n).classList.add('active');event.target.classList.add('active');if(n==='tasks')loadTasks();if(n==='docs')loadDocs();if(n==='jarvis')loadJarvis();}"
    "function toggleOpt(t){if(t==='rag'){useRag=!useRag;document.getElementById('tRag').classList.toggle('on',useRag);}else{useWeb=!useWeb;document.getElementById('tWeb').classList.toggle('on',useWeb);}}"
    "async function sendChat(){const inp=document.getElementById('chatInput');const msg=inp.value.trim();if(!msg)return;inp.value='';addMsg('user',msg);const ld=addMsg('assistant','<span class=\"spinner\"></span>');try{const r=await api('/api/chat',{method:'POST',body:JSON.stringify({message:msg,session_id:sid,use_rag:useRag,use_web:useWeb,mode:'agent'})});var resp=r.response||'(vide)';if(r.mode==='agent'){if(r.plan&&r.plan.length){resp='<div style=\"font-size:11px;color:var(--muted);margin-bottom:8px\">'+('Plan: '+r.plan.map(function(s){return s.type+(s.params.query?' → '+s.params.query:'')}).join(' → '))+'</div>'+resp;}if(r.confidence){resp+='<div style=\"font-size:10px;color:var(--muted);margin-top:8px\">Confiance: '+r.confidence+'</div>';}}ld.innerHTML=formatMarkdown(resp);renderLatex(ld);if(r.tool_calls?.length)r.tool_calls.forEach(tc=>addMsg('system','&#128295; '+tc.tool));if(r.actions?.length)r.actions.forEach(a=>addMsg('system','&#9989; Action: '+a.tool));}catch(e){ld.innerHTML='&#10060; Erreur.';} }"
    "function addMsg(role,html){const b=document.getElementById('chatBox');const d=document.createElement('div');d.className='msg '+role;d.innerHTML=formatMarkdown(html);b.appendChild(d);b.scrollTop=b.scrollHeight;renderLatex(d);return d;}"
    "function formatMarkdown(text){"
    "var blocks=[];"
    "text=text.replace(/\\$\\$([\\s\\S]*?)\\$\\$/g,function(m){blocks.push(m);return'<<LATEX'+(blocks.length-1)+'>>';});"
    "text=text.replace(/\\\\\\[([\\s\\S]*?)\\\\\\]/g,function(m){blocks.push(m);return'<<LATEX'+(blocks.length-1)+'>>';});"
    "text=text.replace(/\\\\begin\\{(pmatrix|bmatrix|vmatrix|matrix|align\\*?|equation\\*?|cases|array|gathered|split)\\*?\\}[\\s\\S]*?\\\\end\\{\\1\\*?\\}/g,function(m){blocks.push(m);return'<<LATEX'+(blocks.length-1)+'>>';});"
    "text=text.replace(/\\*\\*([^*\\n]+?)\\*\\*/g,'<b>$1</b>');"
    "text=text.replace(/(^|\\s)\\*([^*\\n]+?)\\*(?=\\s|$|\\.|,|!|\\?|;|\\))/g,'$1<i>$2</i>');"
    "text=text.replace(/`([^`\\n]+?)`/g,'<code>$1</code>');"
    "text=text.replace(/(\\n|^)[-\\*]\\s+(.+?)(?=\\n[-\\*]|\\n\\n|$)/g,function(_,nl,item){return nl+'<li>'+item+'</li>';});"
    "text=text.replace(/(<li>.*?<\\/li>)/gs,function(m){return'<ul>'+m+'</ul>';});"
    "text=text.replace(/<<LATEX(\\d+)>>/g,function(_,i){return blocks[parseInt(i)];});"
    "return text;}"
    "function renderLatex(el){if(typeof katex==='undefined')return;try{"
    "el.innerHTML=el.innerHTML.replace(/\\\\\\[([\\s\\S]*?)\\\\\\]/g,function(_,m){try{return katex.renderToString(m.trim(),{displayMode:true,throwOnError:false})}catch(e){return _}});"
    "el.innerHTML=el.innerHTML.replace(/\\$\\$([\\s\\S]*?)\\$\\$/g,function(_,m){try{return katex.renderToString(m.trim(),{displayMode:true,throwOnError:false})}catch(e){return _}});"
    "el.innerHTML=el.innerHTML.replace(/\\\\\\(([\\s\\S]*?)\\\\\\)/g,function(_,m){try{return katex.renderToString(m.trim(),{displayMode:false,throwOnError:false})}catch(e){return _}});"
    "el.innerHTML=el.innerHTML.replace(/(^|[^\\\\$])\\$([^\\$\\n]+?)\\$(?=[^\\$]|$)/g,function(_,p,m){try{return p+katex.renderToString(m.trim(),{displayMode:false,throwOnError:false})}catch(e){return _}});"
    "el.innerHTML=el.innerHTML.replace(/\\\\begin\\{(pmatrix|bmatrix|vmatrix|matrix|align\\*?|equation\\*?|cases|array|gathered|split)\\*?\\}([\\s\\S]*?)\\\\end\\{\\1\\*?\\}/g,function(_,env,body){try{return katex.renderToString('\\\\begin{'+env+'}'+body+'\\\\end{'+env+'}',{displayMode:true,throwOnError:false})}catch(e){return _}});"
    "}catch(e){}}"
    "async function loadStatus(){try{const s=await api('/api/status');document.getElementById('ollamaStatus').textContent=s.ollama.model||'Ollama';document.getElementById('ollamaStatus').className='badge'+(s.ollama.running?'':' off');document.getElementById('statDocs').textContent=s.documents.count;document.getElementById('statTodo').textContent=s.tasks.todo||0;document.getElementById('statProg').textContent=s.tasks.in_progress||0;document.getElementById('statDone').textContent=s.tasks.done||0;document.getElementById('statMdl').textContent=s.ollama.model||'?';const ins=await api('/api/insights?limit=5');document.getElementById('statIns').textContent=ins.count||0;const el=document.getElementById('recentIns');if(ins.insights?.length)el.innerHTML=ins.insights.map(i=>`<div class=\"insight-item\"><div>${i.text}</div><div class=\"insight-time\">${(i.timestamp||'').slice(0,16)}</div></div>`).join('');}catch(e){}}"
    "async function loadTasks(){const r=await api('/api/tasks');['todo','in_progress','done'].forEach(st=>{const col=document.getElementById('col-'+st);const ts=r.kanban?.[st]||[];col.innerHTML=ts.length?ts.map(t=>`<div class=\"task-card\"><div class=\"task-title\">${t.title}</div><div class=\"task-meta\">${t.objective||''} ${t.description?('· '+t.description.slice(0,50)):''}</div><div class=\"task-actions\">${st!=='todo'?`<button onclick=\"moveTask(${t.id},'todo')\">&#8592; &Agrave; faire</button>`:''} ${st!=='in_progress'?`<button onclick=\"moveTask(${t.id},'in_progress')\">&#9203; En cours</button>`:''} ${st!=='done'?`<button onclick=\"moveTask(${t.id},'done')\">&#10003; OK</button>`:''}<button onclick=\"delTask(${t.id})\" style=\"color:var(--danger)\">&#10005;</button></div></div>`).join(''):`<div style=\"color:var(--muted);font-size:12px;padding:8px\">Aucune t\u00e2che</div>`;});}"
    "async function createTask(){const t=document.getElementById('ntTitle').value.trim();if(!t)return alert('Titre requis');await api('/api/tasks',{method:'POST',body:JSON.stringify({title:t,description:document.getElementById('ntDesc').value,objective:document.getElementById('ntObj').value})});document.getElementById('ntTitle').value='';document.getElementById('ntDesc').value='';document.getElementById('ntObj').value='';loadTasks();}"
    "async function moveTask(id,st){await api(`/api/tasks/${id}`,{method:'PATCH',body:JSON.stringify({status:st})});loadTasks();}"
    "async function delTask(id){if(!confirm('Supprimer ?'))return;await api(`/api/tasks/${id}`,{method:'DELETE'});loadTasks();}"
    "async function loadDocs(){const r=await api('/api/documents');const el=document.getElementById('docList');if(!r.documents?.length){el.innerHTML='<span style=\"color:var(--muted)\">Aucun document.</span>';return;}el.innerHTML=r.documents.map(d=>`<div class=\"doc-item\"><div class=\"doc-icon\">${d.type}</div><div class=\"doc-name\">${d.name}</div><div class=\"doc-size\">${d.size_kb} Ko</div><button class=\"doc-delete\" onclick=\"delDoc('${d.name}')\">&#10005;</button></div>`).join('');}"
    "async function uploadFiles(files){for(const f of files){const fd=new FormData();fd.append('file',f);const z=document.getElementById('upZone');z.textContent='Envoi de '+f.name+'...';await fetch('/api/documents/upload',{method:'POST',body:fd});z.innerHTML='&#10003; '+f.name+' upload\u00e9. <span style=\"color:var(--muted)\">Ing\u00e9stion en cours...</span>';setTimeout(()=>{z.innerHTML='Cliquez ou glissez vos fichiers ici';loadDocs();},2000);}}"
    "async function delDoc(n){if(!confirm('Supprimer \"'+n+'\"' + ' ?'))return;await api('/api/documents/'+encodeURIComponent(n),{method:'DELETE'});loadDocs();}"
    "async function loadJarvis(){const s=await api('/api/jarvis/status');document.getElementById('jDot').className='dot'+(s.running?' on':'');document.getElementById('jState').textContent=s.running?'Actif':'Inactif';document.getElementById('jToggle').textContent=s.running?'Arr\u00eater':'D\u00e9marrer';document.getElementById('jLastRun').textContent=s.last_run?('Dernier cycle : '+s.last_run.slice(0,16)):'Aucun cycle';const ins=await api('/api/insights?limit=50');document.getElementById('allIns').innerHTML=ins.insights?.length?ins.insights.map(i=>`<div class=\"insight-item\"><div>${i.text}</div><div class=\"insight-time\">${(i.timestamp||'').slice(0,16)}</div></div>`).join(''):'<span style=\"color:var(--muted)\">Aucun insight.</span>';}"
    "async function toggleJarvis(){await api('/api/jarvis/toggle',{method:'POST'});loadJarvis();}"
    "async function runNow(){await api('/api/jarvis/run-now',{method:'POST'});setTimeout(loadJarvis,2000);}"
    "const z=document.getElementById('upZone');"
    "z.addEventListener('dragover',e=>{e.preventDefault();z.style.borderColor='var(--accent)';});"
    "z.addEventListener('dragleave',()=>{z.style.borderColor='';});"
    "z.addEventListener('drop',e=>{e.preventDefault();z.style.borderColor='';uploadFiles(e.dataTransfer.files);});"
    "loadStatus();setInterval(loadStatus,30000);"
    "</script></body></html>"
)