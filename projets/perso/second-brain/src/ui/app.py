"""
Second Brain — Web Dashboard Backend
======================================
Serves the HTML/CSS/JS frontend and provides a REST API
for the UI to interact with the brain.
"""

import os
import threading
import logging
from flask import Flask, jsonify, request, render_template

# Ensure the paths are correctly resolved for the UI templates and static files
from pathlib import Path
import sys

# Append project root to path if needed
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.goals import load_goals
from src.tasks import load_tasks
from src.memory.history import load_memory
from src.ai.llm_client import LLMClient
from src.agent.coordinator import Coordinator
from src.agent.attention import rank_memories

# Configure Flask app paths
UI_DIR = Path(__file__).parent
app = Flask(__name__, 
            template_folder=str(UI_DIR / "templates"),
            static_folder=str(UI_DIR / "static"))

# Global State for the Background Agent
AGENT_THREAD = None
AGENT_STOP_EVENT = threading.Event()
COORDINATOR = None

# Set up logging for Flask
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)
logger = logging.getLogger("ui.backend")

# ─── 1. Background Agent Management ─────────────────────────────────────

def agent_worker(interval: int):
    """Background worker that runs the Coordinator loop."""
    global COORDINATOR
    COORDINATOR = Coordinator()
    logger.info(f"Agent worker started with interval {interval}s")
    
    while not AGENT_STOP_EVENT.is_set():
        try:
            COORDINATOR.run_cycle()
        except Exception as e:
            logger.error(f"Coordinator cycle failed: {e}")
            
        # Sleep with interruption checking
        for _ in range(interval):
            if AGENT_STOP_EVENT.is_set():
                break
            import time
            time.sleep(1)
            
    logger.info("Agent worker stopped.")
    COORDINATOR = None

# ─── 2. Web Endpoints ──────────────────────────────────────────────────

@app.route("/")
def index():
    """Serves the main dashboard HTML."""
    return render_template("index.html")

# ─── 3. REST API ───────────────────────────────────────────────────────

@app.route("/api/stats", methods=["GET"])
def get_stats():
    memories = load_memory()
    tasks = load_tasks()
    goals = load_goals()
    
    pending_tasks = [t for t in tasks if t.get("status") in ["todo", "pending"]]
    done_tasks = [t for t in tasks if t.get("status") == "completed"]
    
    return jsonify({
        "memory_count": len(memories),
        "task_count": len(tasks),
        "pending_tasks": len(pending_tasks),
        "completed_tasks": len(done_tasks),
        "goal_count": len(goals),
        "agent_running": AGENT_THREAD is not None and AGENT_THREAD.is_alive()
    })

@app.route("/api/goals", methods=["GET"])
def api_goals():
    goals = load_goals()
    # Sort by priority
    goals.sort(key=lambda g: g.get("priority", 5), reverse=True)
    return jsonify({"goals": goals})

@app.route("/api/tasks", methods=["GET"])
def api_tasks():
    tasks = load_tasks()
    tasks.sort(key=lambda t: t.get("priority", 5), reverse=True)
    return jsonify({"tasks": tasks})

@app.route("/api/memories", methods=["GET"])
def api_memories():
    memories = load_memory()
    goals = load_goals()
    
    # Optional: We could just send recent memories, or rank them.
    # Let's send the 10 most recent
    recent = memories[-10:] if len(memories) >= 10 else memories
    recent.reverse() # newest first
    return jsonify({"memories": recent})

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json
    question = data.get("question", "")
    use_internet = data.get("use_internet", False)
    
    if not question:
        return jsonify({"error": "Question requise"}), 400
        
    llm = LLMClient()
    memories = load_memory()
    goals = load_goals()
    
    # Grab context from ranked memories
    ranked = rank_memories(memories, goals)
    context_text = "\\n".join([f"- {m.get('question', '')} : {m.get('answer', '')}" for m in ranked[:3]])
    
    # Optional Document Search (RAG)
    try:
        from src.ai.rag_pipeline import RAGPipeline
        rag = RAGPipeline(llm_client=llm)
        retrieved_chunks = rag.retrieve_only(question)
        if retrieved_chunks:
            context_text += "\\n\\n[EXTRAITS DE DOCUMENTS PERTINENTS]\\n"
            for chunk in retrieved_chunks:
                context_text += f"- (Fichier: {chunk['metadata'].get('source_file', 'Inconnu')}) {chunk['content']}\\n"
    except Exception as e:
        logger.error(f"Erreur lors de la récupération RAG: {e}")
        
    # Optional Internet Search Context
    internet_context = ""
    if use_internet:
        try:
            from src.tools.builtin import WebSearchTool
            tool = WebSearchTool()
            res = tool.execute(query=question)
            if res.get("status") == "success" and res.get("formatted_text"):
                internet_context = "\\n\\n[RÉSULTATS INTERNET RÉCENTS]\\n" + res["formatted_text"]
        except Exception as e:
            logger.error(f"Erreur recherche web: {e}")
            
    # Recent Conversation Context (last 4 messages)
    recent_history = ""
    if len(memories) > 0:
        recent = memories[-4:]
        recent_history = "\\n\\n[HISTORIQUE RÉCENT DE LA CONVERSATION]\\n"
        recent_history += "\\n".join([f"User: {m.get('question', '')}\\nAI: {m.get('answer', '')}" for m in recent])
    
    # Initialize tools
    from src.tools import init_all_tools
    init_all_tools()
    
    # Check if we should use a tool (Plugin / Built-in)
    tool_context = ""
    from src.tools.llm_router import route_query
    from src.tools.registry import execute_tool
    
    route_result = route_query(question, context_text, llm=llm)
    if route_result and route_result.get("tool"):
        tool_name = route_result["tool"]
        tool_args = route_result.get("args", {})
        
        # Don't auto-confirm dangerous tools in chat, just execute them directly 
        # for plugins which are safe-write or read-only
        logger.info(f"LLM decided to use tool '{tool_name}' with args {tool_args}")
        try:
            # We auto-confirm in chat UI for simplicity
            exec_res = execute_tool(tool_name, tool_args, confirm_fn=lambda x: True)
            if exec_res.get("status") == "success":
                tool_context = f"\\n\\n[RÉSULTAT DE L'OUTIL '{tool_name}']\\n{exec_res.get('message', '')}\\n{exec_res.get('details', '')}"
            else:
                tool_context = f"\\n\\n[ERREUR DE L'OUTIL '{tool_name}']\\n{exec_res.get('message', '')}"
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            tool_context = f"\\n\\n[ERREUR DE L'OUTIL '{tool_name}']\\n{e}"
    
    system_prompt = f"""
    Tu es un assistant IA local extrêmement direct et concis. 
    RÈGLES IMPORTANTES :
    1. Va TOUJOURS droit au but. Pas de phrases de remplissage ("Voici ce qu'il faut comprendre...", "En résumé...").
    2. Utilise le Markdown pour formater ta réponse de manière lisible.
    3. Pour les mathématiques, utilise TOUJOURS LaTeX. Utilise `$$` pour les équations en bloc (sur leur propre ligne) et `$` pour les équations en ligne.
    4. Réponds toujours en français.

    Voici du contexte pertinent issu des souvenirs profonds :
    {context_text}{internet_context}{recent_history}{tool_context}
    """
    
    try:
        answer = llm.generate(prompt=question, system_prompt=system_prompt)
        
        from src.memory.history import add_interaction
        add_interaction(question, answer)
        
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/documents", methods=["GET"])
def api_documents():
    from src.data_layer.document_manager import DocumentManager
    doc_manager = DocumentManager()
    docs = doc_manager.list_documents()
    return jsonify({"documents": docs})

@app.route("/api/graph", methods=["GET"])
def api_graph():
    # Load all entities
    from src.goals import load_goals
    from src.tasks import load_tasks
    from src.data_layer.document_manager import DocumentManager
    
    goals = load_goals()
    tasks = load_tasks()
    docs = DocumentManager().list_documents()
    
    nodes = []
    edges = []
    
    # Center node
    nodes.append({"id": "center", "label": "Vous", "shape": "image", "image": "https://cdn-icons-png.flaticon.com/512/3135/3135715.png", "size": 40})
    
    # Goal Nodes
    for g in goals:
        nodes.append({"id": g["id"], "label": g["title"], "group": "goals", "shape": "dot", "size": 25})
        edges.append({"from": "center", "to": g["id"]})
        
    # Task Nodes
    for t in tasks:
        nodes.append({"id": t["id"], "label": t["title"], "group": "tasks", "shape": "dot", "size": 15})
        # If task has a specific goal, link to it. Else, link to center
        # Since tasks don't have explicit goal_id in this simplified schema, we link to center
        # Or we can randomly distribute them or check keywords
        edges.append({"from": "center", "to": t["id"]})
        
    # Document Nodes
    for d in docs:
        doc_id = d["id"]
        # Limit label length for better display
        label = d["filename"][:20] + "..." if len(d["filename"]) > 20 else d["filename"]
        nodes.append({"id": doc_id, "label": label, "group": "docs", "shape": "square", "size": 20})
        edges.append({"from": "center", "to": doc_id})
        
    return jsonify({"nodes": nodes, "edges": edges})

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier fourni."}), 400
        
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Nom de fichier vide."}), 400
        
    from config.settings import RAW_DATA_DIR
    import subprocess
    
    # Ensure raw directory exists
    os.makedirs(RAW_DATA_DIR, exist_ok=True)
    
    file_path = RAW_DATA_DIR / file.filename
    file.save(file_path)
    
    # We call the CLI ingest command to parse and store the document in the background
    # This avoids blocking the web server and reuses existing logic
    def ingest_task(path):
        import subprocess
        # Get python executable path
        python_exe = sys.executable
        # Get main.py path
        main_script = str(Path(__file__).parent.parent.parent / "main.py")
        subprocess.run([python_exe, main_script, "ingest", "--file", str(path)])
        
    # Run ingestion in a separate thread so the upload responds immediately
    threading.Thread(target=ingest_task, args=(file_path,), daemon=True).start()
    
    return jsonify({"message": f"Fichier {file.filename} importé et mis en file d'attente pour ingestion."})

@app.route("/api/goals/<goal_id>", methods=["DELETE"])
def api_delete_goal(goal_id):
    from src.goals import delete_goal
    if delete_goal(goal_id):
        return jsonify({"message": "Objectif supprimé."})
    return jsonify({"error": "Objectif non trouvé."}), 404

@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def api_delete_task(task_id):
    from src.tasks import delete_task
    if delete_task(task_id):
        return jsonify({"message": "Tâche supprimée."})
    return jsonify({"error": "Tâche non trouvée."}), 404

@app.route("/api/documents/<doc_id>", methods=["DELETE"])
def api_delete_document(doc_id):
    from src.data_layer.document_manager import DocumentManager
    doc_manager = DocumentManager()
    
    doc = doc_manager.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Document non trouvé."}), 404
        
    # Delete from sqlite
    if doc_manager.delete_document(doc_id):
        # Try to delete actual file
        try:
            import os
            if os.path.exists(doc['filepath']):
                os.remove(doc['filepath'])
        except Exception as e:
            logger.error(f"Failed to delete file {doc['filepath']}: {e}")
            
        return jsonify({"message": "Document supprimé."})
    return jsonify({"error": "Erreur lors de la suppression."}), 500

@app.route("/api/agent/toggle", methods=["POST"])
def api_toggle_agent():
    global AGENT_THREAD, AGENT_STOP_EVENT
    
    if AGENT_THREAD is not None and AGENT_THREAD.is_alive():
        # Stop it
        AGENT_STOP_EVENT.set()
        AGENT_THREAD.join(timeout=2.0)
        AGENT_THREAD = None
        return jsonify({"status": "stopped", "running": False})
    else:
        # Start it
        AGENT_STOP_EVENT.clear()
        req_data = request.get_json(silent=True) or {}
        interval = req_data.get("interval", 3600)
        AGENT_THREAD = threading.Thread(target=agent_worker, args=(interval,), daemon=True)
        AGENT_THREAD.start()
        return jsonify({"status": "started", "running": True})

def start_server(host="127.0.0.1", port=5000):
    logger.info(f"Starting Second Brain Dashboard on http://{host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    start_server()
