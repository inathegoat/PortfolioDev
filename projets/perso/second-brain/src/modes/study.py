"""src/modes/study.py — Study mode: quizzes, flashcards, study plans.

Generates educational content from ingested documents:
- Quiz: N questions with multiple choice or open-ended
- Flashcards: question/answer pairs for spaced repetition
- Study plan: structured revision schedule
"""
import json
import logging
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class QuizQuestion:
    question: str
    options: List[str] = field(default_factory=list)
    correct_index: int = 0
    explanation: str = ""
    source: str = ""


@dataclass
class Flashcard:
    front: str   # question or concept
    back: str    # answer or definition
    source: str = ""
    topic: str = ""


@dataclass
class StudyPlan:
    title: str
    sessions: List[Dict[str, Any]] = field(default_factory=list)
    total_duration_hours: float = 0.0
    sources: List[str] = field(default_factory=list)


class StudyMode:
    """Generates study materials from ingested documents."""

    def __init__(self, llm_client=None, rag_pipeline=None):
        self.llm = llm_client
        self.rag = rag_pipeline

    # ── Quiz ──────────────────────────────────────────────────────────

    def generate_quiz(
        self,
        topic: str,
        num_questions: int = 5,
        question_type: str = "qcm",  # "qcm" or "open"
    ) -> List[QuizQuestion]:
        """Generate quiz questions about a topic from documents."""
        # Retrieve relevant chunks
        chunks = self._retrieve(topic)
        if not chunks:
            return []

        context = "\n".join(
            c.get("content", c.get("text", ""))[:300]
            for c in chunks[:5]
        )

        if question_type == "qcm":
            prompt = (
                f"À partir du contenu suivant, génère exactement {num_questions} questions "
                f"à choix multiples (QCM) avec 4 options chacune. "
                f"Indique la réponse correcte et une brève explication.\n\n"
                f"Format JSON strict :\n"
                f'{{"questions": [{{"question": "...", "options": ["A", "B", "C", "D"], '
                f'"correct_index": 0, "explanation": "..."}}]}}\n\n'
                f"Contenu :\n{context[:2000]}"
            )
        else:
            prompt = (
                f"À partir du contenu suivant, génère exactement {num_questions} questions "
                f"ouvertes avec leur réponse détaillée.\n\n"
                f"Format JSON strict :\n"
                f'{{"questions": [{{"question": "...", "answer": "..."}}]}}\n\n'
                f"Contenu :\n{context[:2000]}"
            )

        try:
            raw = self.llm.generate(
                prompt=prompt,
                system_prompt="Tu es un professeur qui crée des quiz éducatifs. Réponds UNIQUEMENT en JSON.",
                temperature=0.4,
                max_tokens=1000,
            )
            return self._parse_quiz(raw, chunks)
        except Exception as e:
            logger.warning(f"Quiz generation failed: {e}")
            return self._fallback_quiz(topic, chunks[:2])

    def _parse_quiz(self, raw: str, chunks: List[dict]) -> List[QuizQuestion]:
        """Parse quiz JSON from LLM output."""
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start < 0 or end <= start:
            return []
        try:
            data = json.loads(raw[start:end])
            questions = []
            source = chunks[0].get("metadata", {}).get("source_file", "document")
            for q in data.get("questions", []):
                if "answer" in q:
                    # Open question
                    questions.append(QuizQuestion(
                        question=q["question"],
                        options=[q.get("answer", "")],
                        correct_index=0,
                        source=source,
                    ))
                else:
                    questions.append(QuizQuestion(
                        question=q["question"],
                        options=q.get("options", []),
                        correct_index=q.get("correct_index", 0),
                        explanation=q.get("explanation", ""),
                        source=source,
                    ))
            return questions
        except (json.JSONDecodeError, KeyError):
            return []

    def _fallback_quiz(self, topic: str, chunks: List[dict]) -> List[QuizQuestion]:
        """Simple fallback quiz from retrieved chunks."""
        questions = []
        for i, c in enumerate(chunks[:3]):
            content = c.get("content", "")[:200]
            source = c.get("metadata", {}).get("source_file", "document")
            questions.append(QuizQuestion(
                question=f"Que savez-vous sur : {content[:80]}... ?",
                source=source,
            ))
        return questions

    # ── Flashcards ────────────────────────────────────────────────────

    def generate_flashcards(
        self,
        topic: str,
        num_cards: int = 10,
    ) -> List[Flashcard]:
        """Generate flashcards from document content."""
        chunks = self._retrieve(topic)
        if not chunks:
            return []

        context = "\n".join(
            c.get("content", c.get("text", ""))[:200]
            for c in chunks[:8]
        )

        prompt = (
            f"À partir du contenu suivant, crée exactement {num_cards} fiches de révision "
            f"(flashcards). Chaque fiche a un recto (concept/question) et un verso (définition/réponse).\n\n"
            f"Format JSON strict :\n"
            f'{{"flashcards": [{{"front": "concept", "back": "définition"}}]}}\n\n'
            f"Contenu :\n{context[:2500]}"
        )

        try:
            raw = self.llm.generate(
                prompt=prompt,
                system_prompt="Tu es un professeur qui crée des fiches de révision. Réponds UNIQUEMENT en JSON.",
                temperature=0.3,
                max_tokens=1500,
            )
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0:
                data = json.loads(raw[start:end])
                source = chunks[0].get("metadata", {}).get("source_file", "document")
                return [
                    Flashcard(front=c["front"], back=c["back"], source=source, topic=topic)
                    for c in data.get("flashcards", [])
                ]
        except Exception as e:
            logger.warning(f"Flashcard generation failed: {e}")

        # Fallback
        return [
            Flashcard(
                front=f"Définir : {c.get('content', '')[:60]}...",
                back="À compléter avec le document source.",
                source=c.get("metadata", {}).get("source_file", "document"),
                topic=topic,
            )
            for c in chunks[:num_cards]
        ]

    # ── Study Plan ────────────────────────────────────────────────────

    def generate_study_plan(
        self,
        subject: str,
        available_hours: float = 10.0,
        deadline_days: int = 7,
    ) -> StudyPlan:
        """Generate a structured study plan for a subject."""
        chunks = self._retrieve(subject)
        if not chunks:
            return StudyPlan(title=f"Plan d'étude : {subject}")

        # Extract main topics from chunks
        topics = set()
        for c in chunks[:10]:
            text = c.get("content", "")[:300]
            # Simple topic extraction: look for capitalized/titled sections
            import re
            found = re.findall(r'(?:Chapitre|Section|Partie|\d+\.)\s*[:\-]?\s*(.{3,50})', text)
            topics.update(found[:3])

        topics_list = list(topics)[:5] if topics else [f"Réviser {subject}"]
        sources = list(set(
            c.get("metadata", {}).get("source_file", "document")
            for c in chunks[:5]
        ))

        # Generate sessions
        sessions_per_day = max(1, len(topics_list) // deadline_days + 1)
        hours_per_session = round(available_hours / (deadline_days * sessions_per_day), 1)

        sessions = []
        for day in range(1, deadline_days + 1):
            day_topics = topics_list[(day - 1) * sessions_per_day: day * sessions_per_day]
            if not day_topics:
                day_topics = ["Révision générale"]
            sessions.append({
                "day": day,
                "topics": day_topics,
                "duration_hours": hours_per_session,
                "activities": [
                    f"Lire les sections sur : {', '.join(day_topics)}",
                    "Faire des exercices d'application",
                    "Créer des fiches de révision",
                    "Auto-évaluation (quiz)",
                ],
            })

        return StudyPlan(
            title=f"Plan d'étude : {subject}",
            sessions=sessions,
            total_duration_hours=available_hours,
            sources=sources,
        )

    def _retrieve(self, topic: str) -> List[dict]:
        """Retrieve relevant chunks for a topic."""
        if self.rag:
            return self.rag.retrieve_only(topic)
        if hasattr(self, '_vs') and self._vs:
            return self._vs.search(topic, k=10)
        return []
