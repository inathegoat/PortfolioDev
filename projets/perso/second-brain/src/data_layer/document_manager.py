"""
Second Brain — Document Manager
=================================
Manages the lifecycle of documents in the system.

Responsibilities:
- Scan the raw data directory for documents
- Track document metadata in SQLite
- Detect duplicates using file hashing
- Provide CRUD operations for document records

The SQLite database stores metadata ONLY — actual embeddings
are in ChromaDB, and source files stay in data/raw/.
"""

import hashlib
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config.settings import (
    METADATA_DB_PATH,
    RAW_DATA_DIR,
    SUPPORTED_EXTENSIONS,
)

logger = logging.getLogger(__name__)


class DocumentManager:
    """
    Manages document metadata and lifecycle.
    
    Usage:
        dm = DocumentManager()
        new_docs = dm.scan_raw_directory()
        dm.register_document(path_to_file)
        dm.list_documents()
    """
    
    def __init__(self, db_path: Path = METADATA_DB_PATH):
        """
        Initialize the document manager and ensure the DB schema exists.
        
        Args:
            db_path: Path to the SQLite metadata database.
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    # ── Database Setup ──────────────────────────────────────────────
    
    def _init_db(self):
        """Create the documents table if it doesn't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    filepath TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    chunk_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    tags TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()
        logger.info(f"Document database initialized at {self.db_path}")
    
    def _connect(self) -> sqlite3.Connection:
        """Create a new database connection."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Return dict-like rows
        return conn
    
    # ── File Discovery ──────────────────────────────────────────────
    
    def scan_raw_directory(self, directory: Path = RAW_DATA_DIR) -> list[Path]:
        """
        Scan the raw data directory for new, unprocessed documents.
        
        Finds all supported files that haven't been ingested yet
        (based on file hash comparison).
        
        Args:
            directory: Directory to scan. Defaults to data/raw/.
        
        Returns:
            List of Paths to new (unprocessed) files.
        """
        directory = Path(directory)
        
        if not directory.exists():
            logger.warning(f"Directory does not exist: {directory}")
            return []
        
        all_files = []
        for ext in SUPPORTED_EXTENSIONS:
            all_files.extend(directory.rglob(f"*{ext}"))
        
        # Filter out already-ingested files
        new_files = [
            f for f in all_files
            if not self.is_already_ingested(f)
        ]
        
        logger.info(
            f"Scanned {directory}: found {len(all_files)} files, "
            f"{len(new_files)} new"
        )
        
        return sorted(new_files)
    
    # ── Document Registration ───────────────────────────────────────
    
    def register_document(
        self,
        file_path: Path,
        chunk_count: int = 0,
        status: str = "pending",
    ) -> str:
        """
        Register a document in the metadata database.
        
        Generates a UUID for the document and stores its metadata.
        Uses file hash to prevent duplicate registrations.
        
        Args:
            file_path:   Path to the document file.
            chunk_count: Number of chunks (updated after ingestion).
            status:      Document status (pending, ingested, error).
        
        Returns:
            The document ID (UUID string).
        """
        file_path = Path(file_path)
        file_hash = self._compute_hash(file_path)
        
        # Check for existing document with same hash
        existing = self._get_by_hash(file_hash)
        if existing:
            logger.info(
                f"Document already registered: {file_path.name} "
                f"(id={existing['id']})"
            )
            return existing["id"]
        
        doc_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO documents 
                    (id, filename, filepath, file_type, file_hash, 
                     file_size, chunk_count, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    file_path.name,
                    str(file_path.resolve()),
                    file_path.suffix.lstrip(".").lower(),
                    file_hash,
                    file_path.stat().st_size,
                    chunk_count,
                    status,
                    now,
                    now,
                )
            )
            conn.commit()
        
        logger.info(f"Registered document: {file_path.name} (id={doc_id})")
        return doc_id
    
    def update_status(
        self,
        doc_id: str,
        status: str,
        chunk_count: Optional[int] = None,
    ):
        """
        Update a document's status and optionally its chunk count.
        
        Args:
            doc_id:      Document UUID.
            status:      New status (pending, ingested, error).
            chunk_count: Updated chunk count (if provided).
        """
        now = datetime.now(timezone.utc).isoformat()
        
        with self._connect() as conn:
            if chunk_count is not None:
                conn.execute(
                    """
                    UPDATE documents 
                    SET status = ?, chunk_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, chunk_count, now, doc_id)
                )
            else:
                conn.execute(
                    """
                    UPDATE documents 
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (status, now, doc_id)
                )
            conn.commit()
    
    # ── Queries ─────────────────────────────────────────────────────
    
    def is_already_ingested(self, file_path: Path) -> bool:
        """
        Check if a file has already been ingested (by hash).
        
        This prevents re-processing the same file even if it's
        been renamed or moved.
        """
        file_hash = self._compute_hash(file_path)
        return self._get_by_hash(file_hash) is not None
    
    def list_documents(self) -> list[dict]:
        """
        Return all registered documents as a list of dicts.
        
        Returns:
            List of document records with all metadata fields.
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents ORDER BY created_at DESC"
            ).fetchall()
        
        return [dict(row) for row in rows]
    
    def get_document(self, doc_id: str) -> Optional[dict]:
        """Get a single document by its ID."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
        
        return dict(row) if row else None
    
    def get_stats(self) -> dict:
        """
        Get summary statistics about the document collection.
        
        Returns:
            Dict with total_documents, total_chunks, status breakdown.
        """
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM documents"
            ).fetchone()[0]
            
            total_chunks = conn.execute(
                "SELECT COALESCE(SUM(chunk_count), 0) FROM documents"
            ).fetchone()[0]
            
            by_status = conn.execute(
                """
                SELECT status, COUNT(*) as count 
                FROM documents GROUP BY status
                """
            ).fetchall()
            
            by_type = conn.execute(
                """
                SELECT file_type, COUNT(*) as count 
                FROM documents GROUP BY file_type
                """
            ).fetchall()
        
        return {
            "total_documents": total,
            "total_chunks": total_chunks,
            "by_status": {row["status"]: row["count"] for row in by_status},
            "by_type": {row["file_type"]: row["count"] for row in by_type},
        }
    
    # ── Deletion ────────────────────────────────────────────────────
    
    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document record from the metadata database.
        
        Note: This only removes the metadata entry. The caller is
        responsible for also removing chunks from ChromaDB.
        
        Args:
            doc_id: Document UUID.
        
        Returns:
            True if a document was deleted, False if not found.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM documents WHERE id = ?", (doc_id,)
            )
            conn.commit()
            deleted = cursor.rowcount > 0
        
        if deleted:
            logger.info(f"Deleted document record: {doc_id}")
        else:
            logger.warning(f"Document not found for deletion: {doc_id}")
        
        return deleted
    
    def reset(self):
        """
        Delete ALL document records. Use with caution!
        
        This wipes the metadata database. The caller should also
        reset ChromaDB separately.
        """
        with self._connect() as conn:
            conn.execute("DELETE FROM documents")
            conn.commit()
        
        logger.warning("All document records deleted (reset)")
    
    # ── Private Helpers ─────────────────────────────────────────────
    
    def _compute_hash(self, file_path: Path) -> str:
        """
        Compute SHA-256 hash of a file for deduplication.
        
        Reads file in 8KB chunks to handle large files efficiently.
        """
        sha256 = hashlib.sha256()
        
        with open(file_path, "rb") as f:
            while True:
                data = f.read(8192)
                if not data:
                    break
                sha256.update(data)
        
        return sha256.hexdigest()
    
    def _get_by_hash(self, file_hash: str) -> Optional[dict]:
        """Look up a document by its file hash."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE file_hash = ?",
                (file_hash,)
            ).fetchone()
        
        return dict(row) if row else None
