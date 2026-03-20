"""
Smart text chunking utility for long query processing.

Provides intelligent text splitting that preserves sentence boundaries
and maintains semantic coherence across chunks.
"""

import re
from typing import List
from app.logger import get_logger
from app.config import settings

logger = get_logger(__name__)

# Sentence boundary patterns (English and Chinese)
SENTENCE_ENDINGS = re.compile(
    r'([.!?。！？\n]+\s*)',  # Period, exclamation, question marks + optional whitespace
    re.UNICODE
)


def smart_chunk_text(
    text: str,
    chunk_size: int = None,
    overlap: int = None
) -> List[str]:
    """
    Split text into chunks while preserving sentence boundaries.

    Algorithm:
    1. Split text by sentence boundaries
    2. Group sentences into chunks of target size
    3. Add overlap between chunks for context continuity

    Args:
        text: Input text to chunk
        chunk_size: Target chunk size in characters (default: from settings)
        overlap: Overlap size in characters (default: from settings)

    Returns:
        List of text chunks

    Example:
        >>> text = "First sentence. Second sentence. Third sentence."
        >>> chunks = smart_chunk_text(text, chunk_size=30, overlap=10)
        >>> len(chunks)  # Will return appropriate number of chunks
    """
    if chunk_size is None:
        chunk_size = settings.CHUNK_SIZE

    if overlap is None:
        overlap = settings.CHUNK_OVERLAP

    # Validation
    if chunk_size <= overlap:
        raise ValueError(f"chunk_size ({chunk_size}) must be > overlap ({overlap})")

    if chunk_size > settings.MAX_QUERY_LENGTH:
        logger.warning(
            f"chunk_size ({chunk_size}) exceeds MAX_QUERY_LENGTH ({settings.MAX_QUERY_LENGTH}), "
            f"using MAX_QUERY_LENGTH instead"
        )
        chunk_size = settings.MAX_QUERY_LENGTH

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # If text is short enough, return as single chunk
    if len(text) <= chunk_size:
        return [text]

    # Split into sentences
    sentences = _split_into_sentences(text)

    # Build chunks
    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        sentence_len = len(sentence)

        # If single sentence exceeds chunk_size, split it forcefully
        if sentence_len > chunk_size:
            # Add current chunk if not empty
            if current_chunk:
                chunks.append(''.join(current_chunk).strip())
                current_chunk = []
                current_length = 0

            # Split long sentence into multiple chunks
            long_sentence_chunks = _split_long_sentence(sentence, chunk_size)
            chunks.extend(long_sentence_chunks)
            continue

        # If adding this sentence would exceed chunk_size
        if current_length + sentence_len > chunk_size:
            # Save current chunk
            if current_chunk:
                chunks.append(''.join(current_chunk).strip())

            # Start new chunk with overlap from previous chunk
            if overlap > 0 and chunks:
                # Get last N characters from previous chunk for overlap
                prev_chunk = chunks[-1]
                overlap_text = prev_chunk[-overlap:] if len(prev_chunk) > overlap else prev_chunk
                current_chunk = [overlap_text + ' ']
                current_length = len(overlap_text) + 1
            else:
                current_chunk = []
                current_length = 0

        # Add sentence to current chunk
        current_chunk.append(sentence)
        current_length += sentence_len

    # Add final chunk
    if current_chunk:
        chunks.append(''.join(current_chunk).strip())

    # Remove duplicates while preserving order
    chunks = _remove_duplicate_chunks(chunks)

    logger.info(
        f"Chunked text: {len(text)} chars -> {len(chunks)} chunks",
        extra={
            "original_length": len(text),
            "num_chunks": len(chunks),
            "chunk_sizes": [len(c) for c in chunks],
            "chunk_size": chunk_size,
            "overlap": overlap
        }
    )

    return chunks


def _split_into_sentences(text: str) -> List[str]:
    """
    Split text into sentences using regex.

    Preserves sentence endings with the sentence they belong to.
    """
    # Split by sentence endings but keep the delimiters
    parts = SENTENCE_ENDINGS.split(text)

    sentences = []
    i = 0
    while i < len(parts):
        if i + 1 < len(parts):
            # Combine sentence with its ending
            sentence = parts[i] + parts[i + 1]
            sentences.append(sentence)
            i += 2
        else:
            # Last part without ending
            if parts[i].strip():
                sentences.append(parts[i])
            i += 1

    return [s for s in sentences if s.strip()]


def _split_long_sentence(sentence: str, chunk_size: int) -> List[str]:
    """
    Forcefully split a sentence that exceeds chunk_size.

    Tries to split on word boundaries when possible.
    """
    if len(sentence) <= chunk_size:
        return [sentence]

    chunks = []
    words = sentence.split()
    current_chunk = []
    current_length = 0

    for word in words:
        word_len = len(word) + 1  # +1 for space

        # If single word exceeds chunk_size, split it
        if word_len > chunk_size:
            # Add current chunk first
            if current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_length = 0

            # Split long word into character chunks
            for i in range(0, len(word), chunk_size):
                chunks.append(word[i:i + chunk_size])
            continue

        # If adding word would exceed chunk_size
        if current_length + word_len > chunk_size:
            if current_chunk:
                chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_length = word_len
        else:
            current_chunk.append(word)
            current_length += word_len

    # Add final chunk
    if current_chunk:
        chunks.append(' '.join(current_chunk))

    return chunks


def _remove_duplicate_chunks(chunks: List[str]) -> List[str]:
    """
    Remove duplicate chunks while preserving order.

    Uses a set to track seen chunks (case-insensitive).
    """
    seen = set()
    unique_chunks = []

    for chunk in chunks:
        chunk_lower = chunk.lower()
        if chunk_lower not in seen:
            seen.add(chunk_lower)
            unique_chunks.append(chunk)

    return unique_chunks


def estimate_chunk_count(text: str, chunk_size: int = None) -> int:
    """
    Estimate the number of chunks that will be created from text.

    This is a fast estimation that doesn't actually perform chunking.

    Args:
        text: Input text
        chunk_size: Target chunk size (default: from settings)

    Returns:
        Estimated number of chunks
    """
    if chunk_size is None:
        chunk_size = settings.CHUNK_SIZE

    text_length = len(text.strip())

    if text_length <= chunk_size:
        return 1

    # Rough estimation: total_length / (chunk_size - overlap)
    effective_chunk_size = max(chunk_size - settings.CHUNK_OVERLAP, chunk_size // 2)
    estimated = (text_length + effective_chunk_size - 1) // effective_chunk_size

    # Add 10% margin for sentence boundaries
    estimated = int(estimated * 1.1) + 1

    return min(estimated, settings.MAX_CHUNKS + 1)  # +1 to detect "too many chunks" case
