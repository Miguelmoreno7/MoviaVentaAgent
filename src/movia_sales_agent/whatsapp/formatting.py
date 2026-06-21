from __future__ import annotations

import re
from typing import List

DEFAULT_WHATSAPP_CHUNK_LIMIT = 520
HARD_WHATSAPP_CHUNK_LIMIT = 900


def split_whatsapp_messages(
    text: str,
    soft_limit: int = DEFAULT_WHATSAPP_CHUNK_LIMIT,
    hard_limit: int = HARD_WHATSAPP_CHUNK_LIMIT,
) -> List[str]:
    normalized = normalize_whatsapp_text(text)
    if not normalized:
        return []
    blocks = split_blocks(normalized)
    chunks: List[str] = []
    current = ""
    for block in blocks:
        if not current:
            current = block
            continue
        candidate = f"{current}\n\n{block}"
        if len(candidate) <= soft_limit:
            current = candidate
            continue
        chunks.extend(split_oversized_block(current, soft_limit, hard_limit))
        current = block
    if current:
        chunks.extend(split_oversized_block(current, soft_limit, hard_limit))
    return merge_short_chunks([chunk.strip() for chunk in chunks if chunk.strip()], soft_limit, hard_limit)


def normalize_whatsapp_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_blocks(text: str) -> List[str]:
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    if len(blocks) > 1:
        return blocks
    bullet_lines = text.splitlines()
    if len(bullet_lines) > 1 and any(line.lstrip().startswith(("-", "*", "•")) for line in bullet_lines):
        return [line.strip() for line in bullet_lines if line.strip()]
    return [text]


def split_oversized_block(block: str, soft_limit: int, hard_limit: int) -> List[str]:
    if len(block) <= soft_limit:
        return [block]
    sentences = split_sentences(block)
    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > hard_limit:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(split_long_text(sentence, hard_limit))
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= soft_limit:
            current = candidate
        else:
            if current:
                chunks.append(current.strip())
            current = sentence
    if current:
        chunks.append(current.strip())
    return chunks


def split_sentences(text: str) -> List[str]:
    pieces = re.split(r"(?<=[.!?])\s+", text)
    return [piece.strip() for piece in pieces if piece.strip()]


def split_long_text(text: str, limit: int) -> List[str]:
    words = text.split()
    chunks: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip() if current else word
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current.strip())
        if len(word) > limit:
            chunks.extend(word[index : index + limit] for index in range(0, len(word), limit))
            current = ""
        else:
            current = word
    if current:
        chunks.append(current.strip())
    return chunks


def merge_short_chunks(
    chunks: List[str], soft_limit: int, hard_limit: int, min_chars: int = 140
) -> List[str]:
    merged: List[str] = []
    index = 0
    while index < len(chunks):
        current = chunks[index]
        if (
            len(current) < min_chars
            and index + 1 < len(chunks)
            and len(f"{current}\n\n{chunks[index + 1]}") <= hard_limit
        ):
            merged.append(f"{current}\n\n{chunks[index + 1]}")
            index += 2
            continue
        if (
            len(current) < min_chars
            and merged
            and len(f"{merged[-1]}\n\n{current}") <= hard_limit
        ):
            merged[-1] = f"{merged[-1]}\n\n{current}"
        else:
            merged.append(current)
        index += 1
    return merged
