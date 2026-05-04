#!/usr/bin/env python3
"""
Second Brain — CLI Entry Point
================================
Personal AI system for intelligent document retrieval and Q&A.

Commands:
    ingest       Ingest documents from data/raw/ into the system
    query        Ask a question about your documents
    chat         Interactive chat mode with your data
    list         List all ingested documents
    stats        Show system statistics
    delete       Delete a document by ID
    reset        Reset all data (with confirmation)

Usage:
    python main.py ingest                          # Ingest all new documents
    python main.py ingest --file path/to/doc.pdf   # Ingest specific file
    python main.py query "What is X?"              # Ask a question
    python main.py chat                            # Interactive chat
    python main.py list                            # List documents
    python main.py stats                           # System stats
    python main.py delete <doc_id>                 # Delete document
    python main.py reset                           # Reset everything

All data stays local. No external API calls. Full privacy.
"""

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

# ── Setup ───────────────────────────────────────────────────────────

# Add project root to path so imports work
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import (
    RAW_DATA_DIR,
    LLM_MODEL, EMBEDDING_MODEL, AGENT_LOOP_INTERVAL,
    ATTENTION_THRESHOLD, TASKS_FILE, init_directories,
)

# Initialize directories
init_directories()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/second_brain.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("second-brain")

# Rich console for pretty output
console = Console()


# ═══════════════════════════════════════════════════════════════════
#  INGEST COMMAND
# ═══════════════════════════════════════════════════════════════════

def cmd_ingest(args):
    """
    Ingest documents into the system.
    
    Pipeline: Parse → Chunk → Embed → Store
    
    Can ingest all new files from data/raw/ or a specific file.
    Automatically skips already-ingested files (deduplication via hash).
    """
    from src.ingestion.pipeline import IngestionPipeline
    
    console.print(Panel(
        "[bold cyan]📥 Document Ingestion Pipeline[/bold cyan]",
        subtitle="Parse → Chunk → Embed → Store"
    ))
    
    pipeline = IngestionPipeline()
    
    if args.file:
        file_path = Path(args.file).resolve()
        if not file_path.exists():
            console.print(f"[red]❌ File not found: {file_path}[/red]")
            return
        files_to_process = [file_path]
    else:
        from config.settings import RAW_DIR
        if not RAW_DIR.exists():
            console.print(f"[yellow]ℹ️  Directory not found: {RAW_DIR}[/yellow]")
            return
        files_to_process = sorted(
            f for f in RAW_DIR.iterdir()
            if f.is_file() and f.suffix.lower() in {".pdf", ".txt", ".md", ".docx", ".xlsx", ".pptx"}
            and not f.name.startswith(".")
        )
    
    if not files_to_process:
        console.print("[yellow]ℹ️  No documents found to ingest.[/yellow]")
        console.print(
            f"  Place documents in: [cyan]{RAW_DATA_DIR}[/cyan]"
        )
        return
    
    console.print(f"Found [bold]{len(files_to_process)}[/bold] document(s)\n")
    
    success_count = 0
    error_count = 0
    
    for file_path in files_to_process:
        console.print(f"[bold]Processing:[/bold] {file_path.name}")
        try:
            result = pipeline.ingest_file(file_path)
            if result.status == "ingested":
                console.print(f"  [green]✅ Ingested: {result.chunks_count} chunks[/green]\n")
                success_count += 1
            elif result.status == "skipped":
                console.print(f"  [yellow]⏭️  Already ingested, skipping[/yellow]\n")
            else:
                console.print(f"  [red]❌ Error: {result.error}[/red]\n")
                error_count += 1
        except Exception as e:
            console.print(f"  [red]❌ Error: {e}[/red]\n")
            logger.error(f"Failed to ingest {file_path.name}: {e}", exc_info=True)
            error_count += 1
    
    console.print(Panel(
        f"[green]✅ Ingested: {success_count}[/green]  "
        f"[red]❌ Errors: {error_count}[/red]",
        title="Ingestion Complete"
    ))


# ═══════════════════════════════════════════════════════════════════
#  QUERY COMMAND
# ═══════════════════════════════════════════════════════════════════

def cmd_query(args):
    """
    Ask a question about your documents (single query).
    
    Runs the full RAG pipeline with memory:
    1. Load conversation history
    2. Embed your question
    3. Find and clean relevant document chunks
    4. Generate answer using the local LLM
    5. Save interaction to memory
    """
    from src.ai.rag_pipeline import RAGPipeline
    
    question = args.question
    console.print(Panel(
        f"[bold cyan]🔍 Question :[/bold cyan] {question}",
    ))
    
    with console.status("[bold]Réflexion en cours...[/bold]"):
        rag = RAGPipeline()
        response = rag.query(question)
    
    # Display memory status
    if response.memory_used:
        console.print("[dim]🧠 Utilisation de la mémoire[/dim]")
    
    # Display answer
    console.print(Panel(
        Markdown(response.answer),
        title="[bold green]Réponse[/bold green]",
        border_style="green",
    ))
    
    # Display sources
    if response.sources:
        console.print("\n[bold]📚 Sources :[/bold]")
        for i, source in enumerate(response.sources, 1):
            relevance = source.get("relevance", 0)
            relevance_bar = "█" * int(relevance * 10) + "░" * (10 - int(relevance * 10))
            console.print(
                f"  {i}. [cyan]{source['source_file']}[/cyan] "
                f"(chunk {source['chunk_index']}) "
                f"[{relevance_bar}] {relevance:.0%}"
            )


# ═══════════════════════════════════════════════════════════════════
#  CHAT COMMAND
# ═══════════════════════════════════════════════════════════════════

def cmd_chat(args):
    """
    Interactive chat mode with your documents.
    
    Maintains conversation context across turns using persistent memory.
    Past interactions are automatically loaded and injected into prompts.
    Type 'quit', 'exit', or 'q' to end the session.
    """
    from src.ai.rag_pipeline import RAGPipeline
    from src.memory.history import get_memory_stats
    
    # Show memory status on startup
    mem_stats = get_memory_stats()
    mem_count = mem_stats.get("total_interactions", 0)
    mem_info = f"Mémoire : {mem_count} interaction(s) passée(s)" if mem_count else "Aucune mémoire"
    
    console.print(Panel(
        "[bold cyan]💬 Mode Chat Interactif[/bold cyan]\n"
        f"[dim]{mem_info}[/dim]\n"
        "Pose des questions sur tes documents.\n"
        "Tape [bold]quit[/bold], [bold]exit[/bold] ou [bold]q[/bold] pour quitter.",
        border_style="cyan",
    ))
    
    # RAG pipeline handles memory automatically (load + save)
    rag = RAGPipeline()
    
    while True:
        try:
            # Get user input
            console.print()
            question = console.input("[bold green]Toi :[/bold green] ").strip()
            
            if not question:
                continue
            
            if question.lower() in ("quit", "exit", "q"):
                console.print("[dim]Session terminée. À bientôt ! 👋[/dim]")
                break
            
            # Generate response (memory is loaded + saved automatically)
            with console.status("[dim]Réflexion...[/dim]"):
                response = rag.query(question)
            
            # Display response
            console.print(f"\n[bold cyan]🧠 Cerveau :[/bold cyan]")
            console.print(Markdown(response.answer))
            
            # Show sources and memory status inline
            footer_parts = []
            if response.sources:
                source_names = set(s["source_file"] for s in response.sources)
                footer_parts.append(f"Sources: {', '.join(source_names)}")
            if response.memory_used:
                footer_parts.append("🧠 Mémoire active")
            if footer_parts:
                console.print(f"\n[dim]{' | '.join(footer_parts)}[/dim]")
                
        except KeyboardInterrupt:
            console.print("\n[dim]Session terminée. À bientôt ! 👋[/dim]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            logger.error(f"Chat error: {e}", exc_info=True)


# ═══════════════════════════════════════════════════════════════════
#  LIST COMMAND
# ═══════════════════════════════════════════════════════════════════

def cmd_list(args):
    """List all registered documents with their metadata."""
    from src.data_layer.document_manager import DocumentManager
    
    doc_manager = DocumentManager()
    documents = doc_manager.list_documents()
    
    if not documents:
        console.print("[yellow]No documents found. Run 'ingest' first.[/yellow]")
        return
    
    table = Table(title="📄 Ingested Documents", show_lines=True)
    table.add_column("ID", style="dim", max_width=8)
    table.add_column("Filename", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Chunks", justify="right", style="green")
    table.add_column("Status", style="bold")
    table.add_column("Ingested At", style="dim")
    
    for doc in documents:
        status_emoji = {
            "ingested": "✅",
            "pending": "⏳",
            "error": "❌",
        }.get(doc["status"], "❓")
        
        table.add_row(
            doc["id"][:8] + "...",
            doc["filename"],
            doc["file_type"],
            str(doc["chunk_count"]),
            f"{status_emoji} {doc['status']}",
            doc["created_at"][:19],
        )
    
    console.print(table)


# ═══════════════════════════════════════════════════════════════════
#  STATS COMMAND
# ═══════════════════════════════════════════════════════════════════

def cmd_stats(args):
    """Show system statistics including memory info."""
    from src.data_layer.document_manager import DocumentManager
    from src.memory.vector_store import VectorStore
    from src.memory.history import get_memory_stats
    from src.ai.llm_client import LLMClient
    
    console.print(Panel("[bold cyan]📊 System Statistics[/bold cyan]"))
    
    # Document stats
    doc_manager = DocumentManager()
    doc_stats = doc_manager.get_stats()
    
    console.print(f"  [bold]Documents:[/bold]  {doc_stats['total_documents']}")
    console.print(f"  [bold]Chunks:[/bold]     {doc_stats['total_chunks']}")
    
    if doc_stats["by_type"]:
        types_str = ", ".join(
            f"{t}: {c}" for t, c in doc_stats["by_type"].items()
        )
        console.print(f"  [bold]By type:[/bold]    {types_str}")
    
    if doc_stats["by_status"]:
        status_str = ", ".join(
            f"{s}: {c}" for s, c in doc_stats["by_status"].items()
        )
        console.print(f"  [bold]By status:[/bold]  {status_str}")
    
    # Vector store stats
    try:
        vs = VectorStore()
        vs_stats = vs.get_stats()
        console.print(f"\n  [bold]Vector DB:[/bold]  {vs_stats['total_chunks']} vectors stored")
    except Exception as e:
        console.print(f"\n  [bold]Vector DB:[/bold]  [red]Error: {e}[/red]")
    
    # Memory stats
    mem_stats = get_memory_stats()
    mem_count = mem_stats.get("total_interactions", 0)
    console.print(f"\n  [bold]Memory:[/bold]     {mem_count} past interaction(s)")
    if mem_count > 0:
        console.print(f"  [bold]First Q:[/bold]    {mem_stats['first_interaction'][:19]}")
        console.print(f"  [bold]Last Q:[/bold]     {mem_stats['last_interaction'][:19]}")
    
    # LLM status
    console.print(f"\n  [bold]LLM Model:[/bold]      {LLM_MODEL}")
    console.print(f"  [bold]Embed Model:[/bold]    {EMBEDDING_MODEL}")
    
    llm = LLMClient()
    if llm.is_available():
        console.print(f"  [bold]Ollama:[/bold]         [green]✅ Connected[/green]")
    else:
        console.print(f"  [bold]Ollama:[/bold]         [red]❌ Not available[/red]")


# ═══════════════════════════════════════════════════════════════════
#  DELETE COMMAND
# ═══════════════════════════════════════════════════════════════════

def cmd_delete(args):
    """Delete a document from the system (metadata + vectors)."""
    from src.data_layer.document_manager import DocumentManager
    from src.memory.vector_store import VectorStore
    
    doc_id = args.doc_id
    
    doc_manager = DocumentManager()
    doc = doc_manager.get_document(doc_id)
    
    if not doc:
        # Try partial ID match
        documents = doc_manager.list_documents()
        matches = [d for d in documents if d["id"].startswith(doc_id)]
        
        if len(matches) == 1:
            doc = matches[0]
            doc_id = doc["id"]
        elif len(matches) > 1:
            console.print(f"[yellow]Multiple matches for '{doc_id}':[/yellow]")
            for m in matches:
                console.print(f"  {m['id'][:8]}... — {m['filename']}")
            return
        else:
            console.print(f"[red]Document not found: {doc_id}[/red]")
            return
    
    # Confirm deletion
    console.print(f"Delete [cyan]{doc['filename']}[/cyan] ({doc['chunk_count']} chunks)?")
    confirm = console.input("[bold]Type 'yes' to confirm: [/bold]").strip()
    
    if confirm.lower() != "yes":
        console.print("[dim]Cancelled.[/dim]")
        return
    
    # Delete from both stores
    vector_store = VectorStore()
    vector_store.delete_document(doc_id)
    doc_manager.delete_document(doc_id)
    
    console.print(f"[green]✅ Deleted: {doc['filename']}[/green]")


# ═══════════════════════════════════════════════════════════════════
#  RESET COMMAND
# ═══════════════════════════════════════════════════════════════════

def cmd_reset(args):
    """Reset all data (metadata DB + vector store + memory). Requires confirmation."""
    from src.data_layer.document_manager import DocumentManager
    from src.memory.vector_store import VectorStore
    from src.memory.history import clear_memory
    
    console.print(Panel(
        "[bold red]⚠️  WARNING: This will delete ALL data![/bold red]\n"
        "• All document metadata\n"
        "• All vector embeddings\n"
        "• All conversation memory\n\n"
        "[dim]Source files in data/raw/ will NOT be deleted.[/dim]",
        border_style="red",
    ))
    
    confirm = console.input("[bold red]Type 'RESET' to confirm: [/bold red]").strip()
    
    if confirm != "RESET":
        console.print("[dim]Cancelled.[/dim]")
        return
    
    with console.status("Resetting..."):
        DocumentManager().reset()
        VectorStore().reset()
        clear_memory()
    
    console.print("[green]✅ All data has been reset.[/green]")


# ═══════════════════════════════════════════════════════════════════
#  AGENT COMMAND (Phase 3 — Jarvis Mode)
# ═══════════════════════════════════════════════════════════════════

def cmd_agent(args):
    """
    Start the proactive brain loop (Jarvis Mode).
    
    Continuously analyzes memory, detects important patterns,
    generates insights, and executes tasks using the multi-agent system.
    Press Ctrl+C to stop.
    """
    from src.agent.coordinator import Coordinator
    from src.goals import load_goals
    from src.memory.history import load_memory
    from src.tasks import get_pending_tasks as _get_pending
    
    # Show status
    goals = load_goals()
    memories = load_memory()
    pending_tasks = _get_pending()
    interval = args.interval or AGENT_LOOP_INTERVAL
    
    console.print(Panel(
        "[bold cyan]🧠 Mode Jarvis — Architecture Multi-Agents (Phase 7)[/bold cyan]\n\n"
        f"  Objectifs chargés :       [green]{len(goals)}[/green]\n"
        f"  Mémoires chargées :      [green]{len(memories)}[/green]\n"
        f"  Tâches en attente :      [yellow]{len(pending_tasks)}[/yellow]\n"
        f"  Intervalle de boucle :    [yellow]{interval}s[/yellow]\n\n"
        "  [dim]Appuie sur Ctrl+C pour arrêter[/dim]",
        border_style="cyan",
    ))
    
    if not goals:
        console.print(
            "[yellow]⚠️  Aucun objectif défini. Ajoutes-en avec : "
            "python main.py goals --add[/yellow]"
        )
    
    if not memories:
        console.print(
            "[yellow]⚠️  Aucune mémoire. Discute d'abord avec : "
            "python main.py chat[/yellow]"
        )
        return
    
    if args.once:
        console.print("[dim]Exécution d'un cycle multi-agents...[/dim]\n")
        loop = Coordinator()
        result = loop.run_cycle()
        
        tasks_created = len(result.get("new_tasks", []))
        executions = len(result.get("execution_results", []))
        feedbacks = len(result.get("feedback", []))
        
        console.print(Panel(
            f"  Mémoires contextuelles : {len(result.get('important_memories', []))}\n"
            f"  Insights générés :      {len(result.get('insights', []))}\n"
            f"  Tâches planifiées :     {tasks_created}\n"
            f"  Tâches exécutées :      {executions}\n"
            f"  Feedbacks Critic :      {feedbacks}",
            title="[bold green]Cycle Multi-Agent Terminé[/bold green]",
            border_style="green",
        ))
    else:
        loop = Coordinator()
        loop.start(interval=interval)


# ═══════════════════════════════════════════════════════════════════
#  GOALS COMMAND (Phase 3)
# ═══════════════════════════════════════════════════════════════════

def cmd_goals(args):
    """
    Manage user goals.
    
    Lists current goals or adds new ones interactively.
    """
    from src.goals import load_goals, add_goal
    
    if args.add:
        # Interactive goal creation
        console.print(Panel(
            "[bold cyan]🎯 Ajouter un Nouvel Objectif[/bold cyan]",
            border_style="cyan",
        ))
        
        title = console.input("[bold]Titre de l'objectif : [/bold]").strip()
        if not title:
            console.print("[red]Le titre est obligatoire[/red]")
            return
        
        description = console.input("[bold]Description : [/bold]").strip()
        
        try:
            priority = int(console.input("[bold]Priorité (1-10) : [/bold]").strip())
        except ValueError:
            priority = 5
        
        keywords_raw = console.input(
            "[bold]Mots-clés (séparés par des virgules) : [/bold]"
        ).strip()
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        
        # Generate a simple ID
        goals = load_goals()
        goal_id = f"goal_{len(goals) + 1:03d}"
        
        goal = add_goal(
            goal_id=goal_id,
            title=title,
            description=description,
            priority=priority,
            keywords=keywords,
        )
        
        console.print(f"\n[green]✅ Objectif ajouté : {goal['title']}[/green]")
        return
    
    # List goals
    goals = load_goals()
    
    if not goals:
        console.print(
            "[yellow]Aucun objectif défini. "
            "Ajoutes-en un avec : python main.py goals --add[/yellow]"
        )
        return
    
    table = Table(title="🎯 Objectifs", show_lines=True)
    table.add_column("ID", style="dim", max_width=10)
    table.add_column("Titre", style="cyan", max_width=30)
    table.add_column("Priorité", justify="center", style="bold")
    table.add_column("Progression", justify="center")
    table.add_column("Mots-clés", style="dim", max_width=40)
    
    for goal in sorted(goals, key=lambda g: g.get("priority", 0), reverse=True):
        priority = goal.get("priority", 5)
        progress = goal.get("progress", 0)
        
        # Color-code priority
        if priority >= 8:
            priority_str = f"[red]{priority}/10[/red]"
        elif priority >= 5:
            priority_str = f"[yellow]{priority}/10[/yellow]"
        else:
            priority_str = f"[green]{priority}/10[/green]"
        
        # Progress bar
        filled = int(progress / 10)
        bar = "█" * filled + "░" * (10 - filled)
        progress_str = f"{bar} {progress}%"
        
        keywords = ", ".join(goal.get("keywords", [])[:5])
        if len(goal.get("keywords", [])) > 5:
            keywords += "..."
        
        table.add_row(
            goal.get("id", ""),
            goal.get("title", ""),
            priority_str,
            progress_str,
            keywords,
        )
    
    console.print(table)


# ═══════════════════════════════════════════════════════════════════
#  TASKS COMMAND (Phase 4)
# ═══════════════════════════════════════════════════════════════════

def cmd_tasks(args):
    """
    Gérer les tâches du système.
    
    Affiche les tâches, filtre par statut, ou marque comme terminée.
    """
    from src.tasks import load_tasks, update_task_status, get_pending_tasks
    from src.goals import get_goal
    
    # ── Mark task as done ───────────────────────────────────────────
    if args.done:
        task_id = args.done
        # Support partial ID matching
        tasks = load_tasks()
        matched = [t for t in tasks if t["id"].startswith(task_id)]
        
        if not matched:
            console.print(f"[red]❌ Tâche non trouvée : {task_id}[/red]")
            return
        if len(matched) > 1:
            console.print(f"[yellow]⚠️ ID ambigu, {len(matched)} tâches correspondent[/yellow]")
            for t in matched:
                console.print(f"  - {t['id']}: {t['title']}")
            return
        
        task = matched[0]
        update_task_status(task["id"], "done")
        console.print(
            f"[green]✅ Tâche terminée : {task['title']}[/green]"
        )
        return
    
    # ── List tasks ──────────────────────────────────────────────────
    if args.pending:
        tasks = get_pending_tasks()
        table_title = "📋 Tâches en Attente"
    else:
        tasks = load_tasks()
        table_title = "📋 Toutes les Tâches"
    
    if not tasks:
        console.print(
            "[yellow]Aucune tâche. Le système en créera automatiquement "
            "via : python main.py agent --once[/yellow]"
        )
        return
    
    table = Table(title=table_title, show_lines=True)
    table.add_column("ID", style="dim", max_width=14)
    table.add_column("Titre", style="cyan", max_width=30)
    table.add_column("Objectif", style="dim", max_width=20)
    table.add_column("Statut", justify="center")
    table.add_column("Priorité", justify="center", style="bold")
    table.add_column("Étapes", style="dim", max_width=40)
    
    # Sort: pending first, then by priority descending
    status_order = {"pending": 0, "in_progress": 1, "done": 2}
    tasks_sorted = sorted(
        tasks,
        key=lambda t: (
            status_order.get(t.get("status", "pending"), 9),
            -t.get("priority", 0),
        ),
    )
    
    for task in tasks_sorted:
        status = task.get("status", "pending")
        priority = task.get("priority", 5)
        steps = task.get("steps", [])
        
        # Status styling
        if status == "done":
            status_str = "[green]✅ terminée[/green]"
        elif status == "in_progress":
            status_str = "[yellow]🔄 en cours[/yellow]"
        else:
            status_str = "[red]⏳ en attente[/red]"
        
        # Priority color
        if priority >= 8:
            priority_str = f"[red]{priority}/10[/red]"
        elif priority >= 5:
            priority_str = f"[yellow]{priority}/10[/yellow]"
        else:
            priority_str = f"[green]{priority}/10[/green]"
        
        # Steps preview
        if steps:
            steps_preview = "\n".join(
                f"{'✓' if i == 0 and status == 'in_progress' else '·'} {s[:40]}"
                for i, s in enumerate(steps[:3])
            )
            if len(steps) > 3:
                steps_preview += f"\n  (+{len(steps)-3} autres)"
        else:
            steps_preview = "[dim]—[/dim]"
        
        # Goal name
        goal_id = task.get("goal_id", "")
        if goal_id:
            goal = get_goal(goal_id)
            goal_name = goal.get("title", goal_id)[:20] if goal else goal_id
        else:
            goal_name = "[dim]—[/dim]"
        
        table.add_row(
            task.get("id", ""),
            task.get("title", ""),
            goal_name,
            status_str,
            priority_str,
            steps_preview,
        )
    
    console.print(table)
    
    # Summary
    pending = sum(1 for t in tasks if t.get("status") == "pending")
    in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")
    done = sum(1 for t in tasks if t.get("status") == "done")
    console.print(
        f"\n[dim]Total : {len(tasks)} | "
        f"En attente : {pending} | "
        f"En cours : {in_progress} | "
        f"Terminées : {done}[/dim]"
    )


# ═══════════════════════════════════════════════════════════════════
#  TOOLS COMMAND (Phase 5)
# ═══════════════════════════════════════════════════════════════════

def cmd_tools(args):
    """
    Lister les outils ou afficher l'historique d'exécution.
    """
    from src.tools import init_all_tools
    init_all_tools()
    
    from src.tools.registry import list_tools, load_audit_log, execute_tool, cli_confirm
    
    # ── Show audit log ──────────────────────────────────────────────
    if args.log:
        log_entries = load_audit_log()
        if not log_entries:
            console.print("[yellow]Aucune exécution d'outil enregistrée.[/yellow]")
            return
        
        table = Table(title="📝 Historique d'Exécution des Outils", show_lines=True)
        table.add_column("Date", style="dim", max_width=20)
        table.add_column("Outil", style="cyan", max_width=20)
        table.add_column("Statut", justify="center", max_width=12)
        table.add_column("Message", max_width=40)
        table.add_column("Permission", style="dim", max_width=12)
        
        for entry in log_entries[-20:]:  # Show last 20
            ts = entry.get("timestamp", "")[:19].replace("T", " ")
            status = entry.get("result_status", "?")
            
            if status == "success":
                status_str = "[green]✅ succès[/green]"
            elif status == "error":
                status_str = "[red]❌ erreur[/red]"
            elif status == "blocked":
                status_str = "[yellow]🔒 bloqué[/yellow]"
            elif status == "cancelled":
                status_str = "[yellow]⏹ annulé[/yellow]"
            else:
                status_str = status
            
            table.add_row(
                ts,
                entry.get("tool", "?"),
                status_str,
                entry.get("result_message", "")[:40],
                entry.get("permission_level", "?"),
            )
        
        console.print(table)
        console.print(f"\n[dim]Total : {len(log_entries)} exécutions[/dim]")
        return
    
    # ── Test tool routing ───────────────────────────────────────────
    if args.run:
        console.print(f"[dim]Envoi au routeur d'outils...[/dim]\n")
        
        from src.tools.llm_router import route_and_execute
        
        result = route_and_execute(
            user_query=args.run,
            confirm_fn=cli_confirm,
        )
        
        if result is None:
            console.print("[yellow]Le routeur n'a sélectionné aucun outil.[/yellow]")
        else:
            status = result.get("status", "?")
            if status == "success":
                console.print(f"[green]✅ {result.get('message', '')}[/green]")
            else:
                console.print(f"[red]❌ {result.get('message', '')}[/red]")
        return
    
    # ── List available tools ────────────────────────────────────────
    tools = list_tools()
    
    if not tools:
        console.print("[yellow]Aucun outil enregistré.[/yellow]")
        return
    
    table = Table(title="🔧 Outils Disponibles", show_lines=True)
    table.add_column("Outil", style="cyan", max_width=20)
    table.add_column("Description", max_width=40)
    table.add_column("Permission", style="dim", max_width=12)
    table.add_column("Arguments", style="dim", max_width=30)
    
    for tool in tools:
        args_desc = ", ".join(
            f"{k} ({'requis' if v.get('required') else 'opt.'})"
            for k, v in tool.get("args", {}).items()
        )
        
        perm = tool.get("permission_level", "?")
        if perm == "read_only":
            perm_str = "[green]lecture[/green]"
        elif perm == "safe_write":
            perm_str = "[yellow]écriture[/yellow]"
        else:
            perm_str = "[red]restreint[/red]"
        
        table.add_row(
            tool.get("name", "?"),
            tool.get("description", "")[:40],
            perm_str,
            args_desc,
        )
    
    console.print(table)


# ═══════════════════════════════════════════════════════════════════
#  UI DASHBOARD COMMAND (Phase 8)
# ═══════════════════════════════════════════════════════════════════

def cmd_dashboard(args):
    """
    Start the local Web UI Dashboard (Flask server).
    """
    console.print(Panel(
        "[bold cyan]🌟 Second Brain — Web Dashboard[/bold cyan]\n\n"
        "  Démarrage du serveur web local...\n"
        f"  Interface accessible sur : [green]http://{args.host}:{args.port}[/green]\n\n"
        "  [dim]Appuie sur Ctrl+C pour arrêter[/dim]",
        border_style="cyan",
    ))
    
    from src.ui.app import start_server
    start_server(host=args.host, port=args.port)


# ═══════════════════════════════════════════════════════════════════
#  TELEGRAM BOT COMMAND (Phase 11)
# ═══════════════════════════════════════════════════════════════════

def cmd_telegram(args):
    """
    Start the Telegram Bot.
    """
    console.print(Panel(
        "[bold cyan]🌟 Second Brain — Telegram Bot[/bold cyan]\\n\\n"
        "  Démarrage de l'agent Telegram...\\n"
        "  [dim]Appuie sur Ctrl+C pour arrêter[/dim]",
        border_style="cyan",
    ))
    
    from src.ui.telegram_bot import start_telegram_bot
    start_telegram_bot()


# ═══════════════════════════════════════════════════════════════════
#  CLI ARGUMENT PARSER
# ═══════════════════════════════════════════════════════════════════

def main():
    """Main entry point — parse arguments and dispatch to commands."""
    
    parser = argparse.ArgumentParser(
        prog="second-brain",
        description="🧠 Second Brain — Personal AI Knowledge System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py ingest                         Ingest all new documents
  python main.py query "What is X?"             Ask a question
  python main.py chat                           Interactive chat mode
  python main.py dashboard                      Launch the Web UI Dashboard
  python main.py list                           List ingested documents
  python main.py stats                          Show system stats
  python main.py delete <doc_id>                Delete a document
        """,
    )
    
    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands"
    )
    
    # ── ingest ──────────────────────────────────────────────────────
    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Ingest documents into the system"
    )
    ingest_parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="Path to a specific file to ingest"
    )
    ingest_parser.set_defaults(func=cmd_ingest)
    
    # ── query ───────────────────────────────────────────────────────
    query_parser = subparsers.add_parser(
        "query",
        help="Ask a question about your documents"
    )
    query_parser.add_argument(
        "question",
        type=str,
        help="Your question"
    )
    query_parser.set_defaults(func=cmd_query)
    
    # ── chat ────────────────────────────────────────────────────────
    chat_parser = subparsers.add_parser(
        "chat",
        help="Interactive chat with your documents"
    )
    chat_parser.set_defaults(func=cmd_chat)
    
    # ── list ────────────────────────────────────────────────────────
    list_parser = subparsers.add_parser(
        "list",
        help="List all ingested documents"
    )
    list_parser.set_defaults(func=cmd_list)
    
    # ── stats ───────────────────────────────────────────────────────
    stats_parser = subparsers.add_parser(
        "stats",
        help="Show system statistics"
    )
    stats_parser.set_defaults(func=cmd_stats)
    
    # ── delete ──────────────────────────────────────────────────────
    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete a document by ID"
    )
    delete_parser.add_argument(
        "doc_id",
        type=str,
        help="Document ID (or partial ID)"
    )
    delete_parser.set_defaults(func=cmd_delete)
    
    # ── reset ───────────────────────────────────────────────────────
    reset_parser = subparsers.add_parser(
        "reset",
        help="Reset all data (requires confirmation)"
    )
    reset_parser.set_defaults(func=cmd_reset)
    
    # ── agent (Phase 3) ──────────────────────────────────────────────
    agent_parser = subparsers.add_parser(
        "agent",
        help="Start the proactive brain loop (Jarvis Mode)"
    )
    agent_parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single brain cycle and exit"
    )
    agent_parser.add_argument(
        "--interval", "-i",
        type=int,
        default=None,
        help=f"Loop interval in seconds (default: {AGENT_LOOP_INTERVAL})"
    )
    agent_parser.set_defaults(func=cmd_agent)
    
    # ── goals (Phase 3) ──────────────────────────────────────────────
    goals_parser = subparsers.add_parser(
        "goals",
        help="List or manage user goals"
    )
    goals_parser.add_argument(
        "--add",
        action="store_true",
        help="Add a new goal interactively"
    )
    goals_parser.set_defaults(func=cmd_goals)
    
    # ── tasks (Phase 4) ──────────────────────────────────────────────
    tasks_parser = subparsers.add_parser(
        "tasks",
        help="Lister et gérer les tâches"
    )
    tasks_parser.add_argument(
        "--pending",
        action="store_true",
        help="Afficher uniquement les tâches en attente"
    )
    tasks_parser.add_argument(
        "--done",
        type=str,
        default=None,
        metavar="TASK_ID",
        help="Marquer une tâche comme terminée"
    )
    tasks_parser.set_defaults(func=cmd_tasks)
    
    # ── tools (Phase 5) ──────────────────────────────────────────────
    tools_parser = subparsers.add_parser(
        "tools",
        help="Lister les outils ou afficher l'audit log"
    )
    tools_parser.add_argument(
        "--log",
        action="store_true",
        help="Afficher l'historique d'exécution des outils"
    )
    tools_parser.add_argument(
        "--run",
        type=str,
        default=None,
        metavar="QUERY",
        help="Envoyer une requête au routeur d'outils (test)"
    )
    tools_parser.set_defaults(func=cmd_tools)
    
    # ── dashboard (Phase 8) ──────────────────────────────────────────
    dashboard_parser = subparsers.add_parser(
        "dashboard",
        aliases=["ui"],
        help="Lancer l'interface web (Dashboard)"
    )
    dashboard_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Hôte du serveur (défaut: 127.0.0.1)"
    )
    dashboard_parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port du serveur (défaut: 5000)"
    )
    dashboard_parser.set_defaults(func=cmd_dashboard)
    
    # ── telegram (Phase 11) ──────────────────────────────────────────
    telegram_parser = subparsers.add_parser(
        "telegram",
        help="Lancer le bot Telegram"
    )
    telegram_parser.set_defaults(func=cmd_telegram)
    
    # ── Parse and dispatch ──────────────────────────────────────────
    args = parser.parse_args()
    
    if not args.command:
        # No command given — show help + banner
        console.print(Panel(
            "[bold cyan]🧠 Second Brain[/bold cyan]\n"
            "[dim]Personal AI Knowledge System[/dim]\n\n"
            "Your local, private AI assistant that learns from your documents.\n"
            "All data stays on your machine. No cloud. No tracking.\n\n"
            f"[dim]LLM: {LLM_MODEL} | Embeddings: {EMBEDDING_MODEL}[/dim]",
            border_style="cyan",
        ))
        parser.print_help()
        return
    
    # Execute the command
    args.func(args)


if __name__ == "__main__":
    main()
