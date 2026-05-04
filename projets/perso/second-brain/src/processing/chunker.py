"""
Second Brain — Text Chunker
============================
Splits extracted text into overlapping chunks for embedding.

Uses a recursive character splitting strategy:
1. Try to split on paragraph breaks (\\n\\n)
2. Then on line breaks (\\n)
3. Then on sentence ends (. )
4. Then on spaces
5. Last resort: character-level split

This preserves semantic coherence within each chunk while
maintaining overlap between chunks to avoid losing context
at boundaries.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── Data Classes ────────────────────────────────────────────────────

@dataclass
class Chunk:
    """A single text chunk ready for embedding."""
    content: str          # The chunk text
    index: int            # Position in the sequence (0-based)
    metadata: dict = field(default_factory=dict)  # start_char, end_char, doc_id


# ── Separator hierarchy for recursive splitting ─────────────────────
# Ordered from most preferred (paragraph) to least preferred (char)
SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


# ── Public API ──────────────────────────────────────────────────────

def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    doc_id: str = "",
    source_file: str = "",
) -> list[Chunk]:
    """
    Split text into overlapping chunks using recursive character splitting.
    
    The algorithm tries to split on natural boundaries (paragraphs, lines,
    sentences) while keeping each chunk under the size limit. Overlap
    between consecutive chunks ensures context isn't lost at boundaries.
    
    Args:
        text:          The full text to chunk.
        chunk_size:    Maximum characters per chunk.
        chunk_overlap: Number of overlapping characters between chunks.
        doc_id:        Document ID for metadata.
        source_file:   Source filename for metadata.
    
    Returns:
        List of Chunk objects, ordered by position in the text.
    
    Example:
        >>> chunks = chunk_text("Hello world. This is a test.", chunk_size=15, chunk_overlap=5)
        >>> len(chunks)
        2
    """
    if not text or not text.strip():
        logger.warning("Empty text provided to chunker")
        return []
    
    if chunk_overlap >= chunk_size:
        raise ValueError(
            f"Overlap ({chunk_overlap}) must be smaller than "
            f"chunk size ({chunk_size})"
        )
    
    # Perform the recursive split
    raw_chunks = _recursive_split(text, chunk_size, SEPARATORS)
    
    # Apply overlap by merging with previous chunk's tail
    chunks_with_overlap = _apply_overlap(raw_chunks, chunk_overlap)
    
    # Build Chunk objects with metadata
    result = []
    current_pos = 0
    
    for i, chunk_text_content in enumerate(chunks_with_overlap):
        chunk = Chunk(
            content=chunk_text_content.strip(),
            index=i,
            metadata={
                "doc_id": doc_id,
                "source_file": source_file,
                "chunk_index": i,
                "char_count": len(chunk_text_content.strip()),
            }
        )
        
        # Only include non-empty chunks
        if chunk.content:
            result.append(chunk)
        
        current_pos += len(chunk_text_content)
    
    logger.info(
        f"Chunked text into {len(result)} chunks "
        f"(size={chunk_size}, overlap={chunk_overlap})"
    )
    
    return result


# ── Internal: Recursive Splitting ───────────────────────────────────

def _recursive_split(
    text: str,
    chunk_size: int,
    separators: list[str],
) -> list[str]:
    """
    Recursively split text using a hierarchy of separators.
    
    Tries the first separator; if resulting pieces are still too large,
    recurses with the next separator in the hierarchy.
    """
    # Base case: text fits in one chunk
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    
    # Base case: no more separators, force-split by character
    if not separators:
        return _force_split(text, chunk_size)
    
    separator = separators[0]
    remaining_separators = separators[1:]
    
    # Split on current separator
    if separator == "":
        # Empty separator = character-level split
        return _force_split(text, chunk_size)
    
    parts = text.split(separator)
    
    # If splitting didn't help (only 1 part), try next separator
    if len(parts) == 1:
        return _recursive_split(text, chunk_size, remaining_separators)
    
    # Merge small parts together until they hit the size limit
    chunks = []
    current_chunk = ""
    
    for i, part in enumerate(parts):
        # Build the candidate by adding the next part
        if current_chunk:
            candidate = current_chunk + separator + part
        else:
            candidate = part
        
        if len(candidate) <= chunk_size:
            # Still fits — keep building
            current_chunk = candidate
        else:
            # Would exceed limit — flush current chunk
            if current_chunk:
                chunks.append(current_chunk)
            
            # If the part itself is too large, recurse with finer separator
            if len(part) > chunk_size:
                sub_chunks = _recursive_split(
                    part, chunk_size, remaining_separators
                )
                chunks.extend(sub_chunks)
                current_chunk = ""
            else:
                current_chunk = part
    
    # Don't forget the last chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def _force_split(text: str, chunk_size: int) -> list[str]:
    """Split text into fixed-size pieces (last resort)."""
    return [
        text[i:i + chunk_size]
        for i in range(0, len(text), chunk_size)
        if text[i:i + chunk_size].strip()
    ]


def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
    """
    Add overlap between consecutive chunks.
    
    Each chunk (except the first) is prepended with the last `overlap`
    characters from the previous chunk. This ensures context continuity.
    """
    if not chunks or overlap <= 0:
        return chunks
    
    result = [chunks[0]]
    
    for i in range(1, len(chunks)):
        prev_chunk = chunks[i - 1]
        # Take the tail of the previous chunk as overlap prefix
        overlap_text = prev_chunk[-overlap:] if len(prev_chunk) >= overlap else prev_chunk
        result.append(overlap_text + chunks[i])
    
    return result
