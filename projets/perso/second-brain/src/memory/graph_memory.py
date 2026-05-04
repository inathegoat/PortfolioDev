"""src/memory/graph_memory.py — Lightweight concept graph.

Links:
- Documents → Concepts (extracted keywords/topics)
- Concepts → Tasks (which task relates to which concept)
- Concepts → Goals (which goal relates to which concept)
- Documents → Tasks → Goals (transitive relationships)

Stored in SQLite for persistence, with in-memory caching.
"""
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from config.settings import DB_DIR

logger = logging.getLogger(__name__)

GRAPH_DB = DB_DIR / "graph.db"


class GraphMemory:
    """Lightweight knowledge graph linking entities.

    Node types: document, concept, task, goal
    Edge types: contains, relates_to, depends_on, part_of
    """

    def __init__(self):
        self._init_db()

    def _connect(self):
        return sqlite3.connect(GRAPH_DB)

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id      TEXT PRIMARY KEY,
                    type    TEXT NOT NULL,   -- document, concept, task, goal
                    label   TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS edges (
                    source  TEXT NOT NULL,
                    target  TEXT NOT NULL,
                    relation TEXT NOT NULL,  -- contains, relates_to, depends_on, part_of
                    weight  REAL DEFAULT 1.0,
                    metadata TEXT DEFAULT '{}',
                    PRIMARY KEY (source, target, relation),
                    FOREIGN KEY (source) REFERENCES nodes(id),
                    FOREIGN KEY (target) REFERENCES nodes(id)
                );
                CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
                CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
                CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
            """)
            conn.commit()

    # ── Node operations ──────────────────────────────────────────────

    def add_node(self, node_id: str, node_type: str, label: str, metadata: Optional[Dict] = None):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO nodes (id, type, label, metadata, created_at) VALUES (?,?,?,?,?)",
                (node_id, node_type, label, str(metadata or {}), datetime.now().isoformat()),
            )
            conn.commit()

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        return dict(row) if row else None

    def get_nodes_by_type(self, node_type: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM nodes WHERE type=? ORDER BY label", (node_type,)
            ).fetchall()
        return [dict(r) for r in rows]

    def delete_node(self, node_id: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM edges WHERE source=? OR target=?", (node_id, node_id))
            conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))
            conn.commit()

    # ── Edge operations ──────────────────────────────────────────────

    def add_edge(self, source: str, target: str, relation: str, weight: float = 1.0):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO edges (source, target, relation, weight) VALUES (?,?,?,?)",
                (source, target, relation, weight),
            )
            conn.commit()

    def get_neighbors(
        self,
        node_id: str,
        relation: Optional[str] = None,
        direction: str = "both",
    ) -> List[Dict[str, Any]]:
        """Get neighbors of a node.

        Args:
            node_id: The node to query.
            relation: Filter by relation type (optional).
            direction: "out" (source→target), "in" (target→source), "both".
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = []
            where = ""
            params: List[str] = []

            if relation:
                where = " AND e.relation=?"
                params = [relation]

            if direction in ("out", "both"):
                rows.extend(conn.execute(
                    f"SELECT e.*, n.label as target_label, n.type as target_type "
                    f"FROM edges e JOIN nodes n ON e.target = n.id "
                    f"WHERE e.source=?{where}",
                    [node_id] + params,
                ).fetchall())

            if direction in ("in", "both"):
                rows.extend(conn.execute(
                    f"SELECT e.*, n.label as source_label, n.type as source_type "
                    f"FROM edges e JOIN nodes n ON e.source = n.id "
                    f"WHERE e.target=?{where}",
                    [node_id] + params,
                ).fetchall())

        return [dict(r) for r in rows]

    def get_related_documents(self, concept: str) -> List[str]:
        """Get documents related to a concept."""
        neighbors = self.get_neighbors(concept, relation="contains", direction="in")
        return [
            n.get("source", n.get("target", ""))
            for n in neighbors
        ]

    def get_related_concepts(self, document_id: str) -> List[str]:
        """Get concepts contained in a document."""
        neighbors = self.get_neighbors(document_id, relation="contains", direction="out")
        return [
            n.get("target_label", n.get("target", ""))
            for n in neighbors
        ]

    def get_related_tasks(self, concept: str) -> List[str]:
        """Get tasks related to a concept."""
        neighbors = self.get_neighbors(concept, relation="relates_to", direction="both")
        return [
            n.get("target_label", n.get("source_label", ""))
            for n in neighbors
        ]

    # ── High-level operations ────────────────────────────────────────

    def link_document_concepts(self, document_id: str, concepts: List[str]):
        """Link a document to its extracted concepts."""
        doc_label = document_id.replace("_", " ")
        self.add_node(document_id, "document", doc_label)
        for concept in concepts:
            concept_id = f"concept_{concept.lower().replace(' ', '_')}"
            self.add_node(concept_id, "concept", concept)
            self.add_edge(document_id, concept_id, "contains")

    def link_task_concept(self, task_id: str, task_title: str, concept: str):
        """Link a task to a concept it relates to."""
        concept_id = f"concept_{concept.lower().replace(' ', '_')}"
        self.add_node(task_id, "task", task_title)
        if not self.get_node(concept_id):
            self.add_node(concept_id, "concept", concept)
        self.add_edge(task_id, concept_id, "relates_to")

    def link_goal_concept(self, goal_id: str, goal_title: str, concepts: List[str]):
        """Link a goal to its concepts."""
        self.add_node(goal_id, "goal", goal_title)
        for concept in concepts:
            concept_id = f"concept_{concept.lower().replace(' ', '_')}"
            if not self.get_node(concept_id):
                self.add_node(concept_id, "concept", concept)
            self.add_edge(goal_id, concept_id, "part_of")

    def extract_concepts_from_text(self, text: str, max_concepts: int = 10) -> List[str]:
        """Simple keyword extraction from text (no LLM needed)."""
        import re
        # Extract capitalized phrases and important-sounding n-grams
        words = re.findall(r'\b[A-ZÀ-Ü][a-zà-ü]+\b', text)
        # Also extract longer words as potential concepts
        long_words = re.findall(r'\b[a-zà-ü]{5,}\b', text.lower())
        # Combine and deduplicate
        concepts = list(dict.fromkeys(words[:5] + long_words[:max_concepts]))
        return concepts[:max_concepts]

    def summary(self) -> Dict[str, Any]:
        """Get graph statistics."""
        with self._connect() as conn:
            nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            by_type = {}
            for row in conn.execute("SELECT type, COUNT(*) FROM nodes GROUP BY type").fetchall():
                by_type[row[0]] = row[1]
        return {
            "total_nodes": nodes,
            "total_edges": edges,
            "nodes_by_type": by_type,
        }
