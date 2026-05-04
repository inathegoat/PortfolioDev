"""
Second Brain — RAG Pipeline (Phase 4)
=======================================
Retrieval-Augmented Generation with conversation memory, reranking,
mandatory citations, tracing, and prompt injection detection.

Improvements over Phase 2:
- Cross-encoder/LLM reranking for better retrieval
- Mandatory structured citations in every answer
- Pipeline tracing with per-step timing
- Summarized conversation memory (not just raw history)
- Basic prompt injection detection
"""
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from config.settings import TOP_K
from src.processing.embedder import Embedder
from src.memory.vector_store import VectorStore
from src.memory.history import add_interaction, format_history_for_prompt
from src.ai.llm_client import LLMClient
from src.retrieval.reranker import Reranker
from src.core.errors import SecurityError
from src.core.metrics import get_collector, QueryMetrics

logger = logging.getLogger(__name__)

# ── System Prompt ────────────────────────────────────────────────────

SYSTEM_PROMPT_V3 = """Tu es un assistant qui répond UNIQUEMENT à partir des extraits de documents fournis.

RÈGLES STRICTES — tu DOIS les suivre :
1. Utilise EXCLUSIVEMENT les informations des sections "CONNAISSANCES RÉCUPÉRÉES".
2. N'invente JAMAIS d'informations, d'exemples, de formules ou de calculs qui ne sont pas dans le contexte.
3. Si le contexte ne contient pas la réponse, dis EXACTEMENT : "Je ne trouve pas cette information dans vos documents."
4. Pour chaque information issue d'un document, cite-la : [Source: nom_fichier].
5. N'ajoute PAS de connaissances externes, même si tu les connais.
6. Si le contexte mentionne un concept sans le détailler, NE comble PAS les trous.
7. Sois concis. Réponds en français.

INTERDICTIONS :
- NE PAS donner d'exemples numériques inventés
- NE PAS créer de matrices, équations ou calculs qui ne sont PAS dans le contexte
- NE PAS faire de développement mathématique non présent dans les documents
- NE PAS répondre "selon vos documents" puis ajouter du contenu inventé
"""

# ── Relevance ────────────────────────────────────────────────────────

RELEVANCE_THRESHOLD = 0.8

# ── Injection patterns ───────────────────────────────────────────────

_INJECTION_PATTERNS = [
    r"(ignore|oublie|forget|disregard)\s+(all|toutes)\s+(previous|précédentes)?\s*(instructions?|règles?)",
    r"(ignore|oublie)\s+(toutes\s+)?(les\s+)?(instructions?|règles?|contraintes?)",
    r"(you are now|tu es maintenant|agis comme|act as|pretend you are|fais semblant d'être)",
    r"(system\s*prompt|system\s*message)\s*:",
    r"<\|im_start\|>|<\|im_end\|>",
    r"\[INST\]|\[/INST\]",
    r"\[SYS\]|\[/SYS\]",
    r"(ignore|forget|oublie|disregard)\s+all\s+(constraints|règles|contraintes)",
]


def detect_injection(text: str, strict: bool = False) -> Optional[str]:
    """Detect prompt injection attempts in user input.

    Returns the matched pattern description, or None if clean.
    If strict=True, raises SecurityError on detection.
    """
    text_lower = text.lower()
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, text_lower):
            msg = f"Potential prompt injection detected: pattern='{pattern}'"
            logger.warning(msg)
            if strict:
                raise SecurityError(msg)
            return pattern
    return None


# ── Data classes ─────────────────────────────────────────────────────

@dataclass
class RAGResponse:
    """Result of a RAG query."""
    answer: str
    sources: list[dict] = field(default_factory=list)
    query: str = ""
    num_chunks_used: int = 0
    memory_used: bool = False
    trace: Optional["PipelineTrace"] = None
    injection_warning: Optional[str] = None
    confidence: str = "low"          # "high", "medium", "low"
    confidence_score: float = 0.0   # 0.0 to 1.0
    missing_information: list[str] = field(default_factory=list)  # what's missing
    self_evaluation: str = ""       # explanation of confidence


@dataclass
class PipelineTrace:
    """Per-step timing and metadata for pipeline debugging."""
    question: str = ""
    start_time: float = 0.0
    steps: List[Dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, duration_ms: float, **meta):
        self.steps.append({"step": name, "duration_ms": round(duration_ms, 1), **meta})

    def total_ms(self) -> float:
        return round((time.time() - self.start_time) * 1000, 1)

    def summary(self) -> str:
        lines = [f"Trace ({self.total_ms()}ms total):"]
        for s in self.steps:
            extras = " ".join(f"{k}={v}" for k, v in s.items() if k not in ("step", "duration_ms"))
            lines.append(f"  {s['step']}: {s['duration_ms']}ms {extras}")
        return "\n".join(lines)


# ── RAG Pipeline ─────────────────────────────────────────────────────

class RAGPipeline:
    """Orchestrates the full RAG pipeline with reranking, citations, tracing."""

    def __init__(
        self,
        embedder: Embedder = None,
        vector_store: VectorStore = None,
        llm_client: LLMClient = None,
        top_k: int = TOP_K,
        memory_limit: int = 5,
        use_reranker: bool = True,
        detect_injections: bool = True,
        use_hybrid_search: bool = True,
        hybrid_alpha: float = 0.7,
    ):
        self.embedder = embedder or Embedder()
        self.vector_store = vector_store or VectorStore()
        self.llm_client = llm_client or LLMClient()
        self.top_k = top_k
        self.memory_limit = memory_limit
        self.use_reranker = use_reranker
        self.detect_injections = detect_injections
        self.use_hybrid_search = use_hybrid_search
        self.hybrid_alpha = hybrid_alpha
        self.reranker = Reranker(self.llm_client) if use_reranker else None
        self._hybrid_searcher = None  # lazy init

    def query(self, question: str, save_to_memory: bool = True) -> RAGResponse:
        trace = PipelineTrace(question=question, start_time=time.time())

        if not question.strip():
            return RAGResponse(answer="Posez une question.", query=question)

        # ── Injection check ───────────────────────────────────────────
        injection_warning = None
        if self.detect_injections:
            injection_warning = detect_injection(question, strict=False)
            if injection_warning:
                logger.warning(f"Injection detection triggered: {injection_warning}")

        # ── Step 1: Memory ────────────────────────────────────────────
        t0 = time.time()
        history_text = format_history_for_prompt(limit=self.memory_limit)
        has_memory = bool(history_text)
        trace.add("memory_load", (time.time() - t0) * 1000, has_history=has_memory)

        # ── Step 2: Summarize memory if too long ─────────────────────
        t0 = time.time()
        if history_text and len(history_text) > 2000:
            history_text = self._summarize_history(history_text)
        trace.add("memory_summarize", (time.time() - t0) * 1000)

        # ── Step 3: Embed ─────────────────────────────────────────────
        t0 = time.time()
        query_embedding = self.embedder.embed_query(question)
        trace.add("embed", (time.time() - t0) * 1000)

        # ── Step 4: Retrieve ──────────────────────────────────────────
        t0 = time.time()
        fetch_k = min(self.top_k + 10, 20)

        if self.use_hybrid_search:
            if self._hybrid_searcher is None:
                from src.retrieval.hybrid_search import HybridSearcher
                self._hybrid_searcher = HybridSearcher(
                    self.vector_store, alpha=self.hybrid_alpha
                )
            raw_results = self._hybrid_searcher.search(query=question, top_k=fetch_k)
        else:
            raw_results = self.vector_store.query(
                query_embedding=query_embedding,
                top_k=fetch_k,
            )
        trace.add("retrieve", (time.time() - t0) * 1000,
                   raw_count=len(raw_results), hybrid=self.use_hybrid_search)

        # ── Step 5: Clean ─────────────────────────────────────────────
        t0 = time.time()
        results = self._clean_and_dedup(raw_results)
        trace.add("clean", (time.time() - t0) * 1000, after_clean=len(results))

        # ── Step 6: Rerank ────────────────────────────────────────────
        t0 = time.time()
        if self.reranker and len(results) > self.top_k:
            results = self.reranker.mmr(results, top_k=min(self.top_k + 2, len(results)))
        trace.add("rerank", (time.time() - t0) * 1000, after_rerank=len(results))

        results = results[:self.top_k]

        # ── Step 6.5: Self-evaluation ─────────────────────────────────
        t0 = time.time()
        confidence, confidence_score, self_eval, missing = self._self_evaluate(
            question, results
        )
        trace.add("self_eval", (time.time() - t0) * 1000,
                   confidence=confidence, score=confidence_score)

        if not results:
            return RAGResponse(
                answer=(
                    "Je n'ai pas trouvé d'information pertinente dans vos "
                    "documents. Vérifiez que des documents ont été ingérés "
                    "avec : python main.py ingest"
                ),
                query=question,
                memory_used=has_memory,
                trace=trace,
                confidence="low",
                confidence_score=0.0,
                missing_information=["Aucun document pertinent trouvé."],
                self_evaluation="Aucun chunk récupéré.",
            )

        if confidence == "low":
            return RAGResponse(
                answer=(
                    "Je ne trouve pas assez d'information dans vos documents "
                    "pour répondre à cette question de manière fiable."
                    + (f"\n\nÉléments manquants : {', '.join(missing)}" if missing else "")
                ),
                query=question,
                sources=[
                    {
                        "source_file": r["metadata"].get("source_file", "unknown"),
                        "chunk_index": r["metadata"].get("chunk_index", -1),
                        "relevance": round(1 - r.get("distance", 0.5), 3),
                        "preview": (
                            r["content"][:200] + "..."
                            if len(r.get("content", "")) > 200
                            else r.get("content", "")
                        ),
                    }
                    for r in results
                ],
                memory_used=has_memory,
                trace=trace,
                confidence="low",
                confidence_score=confidence_score,
                missing_information=missing,
                self_evaluation=self_eval,
            )
            return RAGResponse(
                answer=(
                    "Je n'ai pas trouvé d'information pertinente dans vos documents. "
                    "Vérifiez que des documents ont été ingérés avec : python main.py ingest"
                ),
                query=question,
                memory_used=has_memory,
                trace=trace,
            )

        # ── Step 7: Build prompt ─────────────────────────────────────
        t0 = time.time()
        prompt = self._build_prompt(question, results, history_text)
        trace.add("build_prompt", (time.time() - t0) * 1000)

        # ── Step 8: Generate ──────────────────────────────────────────
        t0 = time.time()
        try:
            answer = self.llm_client.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_V3,
                temperature=0.3,
            )
        except ConnectionError:
            answer = "Impossible de se connecter à Ollama. Lancez : ollama serve"
        except Exception as e:
            answer = f"Erreur lors de la génération : {e}"
        trace.add("generate", (time.time() - t0) * 1000, answer_len=len(answer))

        # ── Step 9: Enforce citations ─────────────────────────────────
        t0 = time.time()
        answer = self._enforce_citations(answer, results)
        trace.add("citations", (time.time() - t0) * 1000)

        # ── Step 10: Save ─────────────────────────────────────────────
        if save_to_memory and not answer.startswith(("Impossible", "Erreur")):
            add_interaction(question, answer)

        # ── Build sources ─────────────────────────────────────────────
        sources = [
            {
                "source_file": r["metadata"].get("source_file", "unknown"),
                "chunk_index": r["metadata"].get("chunk_index", -1),
                "relevance": round(1 - r.get("distance", 0.5), 3),
                "preview": (
                    r["content"][:200] + "..."
                    if len(r.get("content", "")) > 200
                    else r.get("content", "")
                ),
            }
            for r in results
        ]

        logger.debug(trace.summary())

        # ── Record metrics ────────────────────────────────────────────
        try:
            get_collector().record_query(QueryMetrics(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
                question=question[:100],
                answer_len=len(answer),
                latency_ms=trace.total_ms(),
                chunks_retrieved=len(raw_results) if raw_results else 0,
                chunks_used=len(results),
                sources=sources_found,
            ))
        except Exception:
            pass

        return RAGResponse(
            answer=answer,
            sources=sources,
            query=question,
            num_chunks_used=len(results),
            memory_used=has_memory,
            trace=trace,
            injection_warning=injection_warning,
            confidence=confidence,
            confidence_score=confidence_score,
            missing_information=missing,
            self_evaluation=self_eval,
        )

    def retrieve_only(self, question: str) -> list[dict]:
        query_embedding = self.embedder.embed_query(question)
        raw = self.vector_store.query(query_embedding=query_embedding, top_k=self.top_k + 10)
        results = self._clean_and_dedup(raw)
        if self.reranker:
            results = self.reranker.mmr(results, top_k=self.top_k)
        return results[:self.top_k]

    # ── Private methods ───────────────────────────────────────────────

    def _clean_and_dedup(self, results: list[dict]) -> list[dict]:
        cleaned = []
        seen = set()
        for r in results:
            content = r.get("content", "").strip()
            if not content or len(content) < 20:
                continue
            distance = r.get("distance", 1.0)
            if distance > RELEVANCE_THRESHOLD:
                continue
            fp = content[:100].lower().strip()
            if fp in seen:
                continue
            seen.add(fp)
            cleaned.append(r)
        cleaned.sort(key=lambda x: x.get("distance", 1.0))
        return cleaned

    def _self_evaluate(
        self, question: str, results: list[dict]
    ) -> tuple[str, float, str, list[str]]:
        """Self-evaluate: can we answer reliably from these chunks?

        Returns:
            (confidence_label, confidence_score, explanation, missing_info)
        """
        if not results:
            return ("low", 0.0, "Aucun chunk récupéré.", ["Aucun document pertinent."])

        # Compute metrics
        num_chunks = len(results)
        avg_relevance = sum(1 - r.get("distance", 0.5) for r in results) / num_chunks

        # Check keyword overlap between question and chunks
        question_words = set(w.lower() for w in question.split() if len(w) > 2)
        all_content = " ".join(r.get("content", "") for r in results).lower()
        matched_words = [w for w in question_words if w in all_content]
        keyword_coverage = len(matched_words) / len(question_words) if question_words else 0

        missing = []
        if keyword_coverage < 0.3:
            missing.append("Peu de mots-clés de la question trouvés dans les documents.")

        # Confidence scoring
        score = 0.0
        score += min(avg_relevance, 1.0) * 0.4     # 40%: relevance quality
        score += min(num_chunks / 3, 1.0) * 0.3     # 30%: enough chunks
        score += min(keyword_coverage, 1.0) * 0.3    # 30%: keyword coverage

        if score >= 0.7:
            confidence = "high"
        elif score >= 0.4:
            confidence = "medium"
        else:
            confidence = "low"

        # Hard rules: force low if keyword coverage is terrible
        if keyword_coverage < 0.2 and avg_relevance < 0.45:
            confidence = "low"
            missing.append("Aucun mot-clé pertinent trouvé dans les documents.")

        if avg_relevance < 0.4:
            missing.append("Pertinence moyenne des chunks trop faible.")
        if num_chunks < 2:
            missing.append("Très peu de chunks récupérés.")
        if confidence == "medium" and len(results) == 1:
            missing.append("Un seul chunk trouvé — information peut être incomplète.")

        explanation = (
            f"chunks={num_chunks}, relevance={avg_relevance:.2f}, "
            f"keyword_cov={keyword_coverage:.2f} → score={score:.2f} ({confidence})"
        )

        return (confidence, round(score, 3), explanation, missing)

    def _summarize_history(self, history_text: str) -> str:
        """Summarize long conversation history to keep context manageable."""
        try:
            prompt = (
                f"Résume cet historique de conversation en 3-5 points clés, en français :\n\n"
                f"{history_text[:3000]}\n\n"
                f"Résumé (points clés) :"
            )
            summary = self.llm_client.generate(prompt=prompt, temperature=0.1, max_tokens=300)
            return summary if summary else history_text[:1000]
        except Exception:
            return history_text[:1000]

    def _build_prompt(
        self,
        question: str,
        context_results: list[dict],
        history_text: str = "",
    ) -> str:
        sections = []

        if history_text:
            sections.append(
                "=== HISTORIQUE ===\n"
                f"{history_text}\n"
                "=== FIN HISTORIQUE ==="
            )

        parts = []
        for i, r in enumerate(context_results, 1):
            source = r["metadata"].get("source_file", "unknown")
            content = r.get("content", "")
            relevance = round(1 - r.get("distance", 0.5), 2)
            parts.append(f"[Document {i}: {source} (pertinence: {relevance:.0%})]\n{content}")
        context_text = "\n\n---\n\n".join(parts)

        sections.append(
            "=== CONNAISSANCES RÉCUPÉRÉES ===\n"
            f"{context_text}\n"
            "=== FIN CONNAISSANCES ==="
        )

        sections.append(f"Question: {question}")

        return "\n\n".join(sections)

    def _enforce_citations(self, answer: str, results: list[dict]) -> str:
        """Ensure citations are present. Add them if the LLM omitted them.
        
        Also strips LaTeX/math blocks that don't appear in any retrieved chunk
        (hallucination guard).
        """
        source_names = {
            r["metadata"].get("source_file", "unknown")
            for r in results
        }

        # ── Hallucination guard: strip ungrounded LaTeX math ─────────
        answer = self._strip_ungrounded_math(answer, results)

        # Check if answer already has citations
        has_citation = bool(re.search(r"\[Source:", answer, re.IGNORECASE))
        if has_citation:
            return answer

        # Check if answer contains any source filename
        for name in source_names:
            if name != "unknown" and name.lower() in answer.lower():
                return answer  # implicit reference is acceptable

        # No citations at all — append sources (unless answer says "ne trouve pas")
        if source_names and source_names != {"unknown"}:
            if re.search(r"ne trouve pas|ne contient pas|pas trouv|aucune information",
                         answer, re.IGNORECASE):
                return answer  # don't append sources to "no info" responses
            names = ", ".join(sorted(source_names))
            return f"{answer}\n\nSources consultées : {names}"

        return answer

    def _strip_ungrounded_math(self, answer: str, results: list[dict]) -> str:
        """Remove LaTeX math blocks that don't appear in any retrieved chunk."""
        # Find all LaTeX blocks
        latex_pattern = re.compile(
            r'(\\\[.*?\\\])|(\\\(.*?\\\))|(\$\$.*?\$\$)|(\\begin\{.*?\}.*?\\end\{.*?\})',
            re.DOTALL,
        )
        all_chunks_text = " ".join(r.get("content", "") for r in results)

        def replacement(match):
            block = match.group(0)
            # Check if any meaningful part of this block appears in chunks
            # Strip LaTeX commands and check if numbers/keywords match
            plain = re.sub(r'\\[a-zA-Z]+', '', block)
            plain = re.sub(r'[{}\[\]&]', ' ', plain)
            words = [w for w in plain.split() if len(w) > 2]
            if not words:
                return block  # pure markup, keep it

            # If most unique words appear in chunks, it's grounded
            grounded = sum(1 for w in set(words[:10]) if w in all_chunks_text)
            if grounded >= max(2, len(set(words[:10])) * 0.3):
                return block

            logger.warning(f"Stripping ungrounded LaTeX: {block[:80]}...")
            return ""

        return latex_pattern.sub(replacement, answer)
