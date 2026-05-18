from __future__ import annotations


def chunk_text(text: str, *, max_chars: int = 1600, overlap_chars: int = 200) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be between 0 and max_chars")

    chunks: list[str] = []
    start = 0
    length = len(normalized)

    while start < length:
        hard_end = min(start + max_chars, length)
        end = hard_end

        if hard_end < length:
            lower_bound = start + max_chars // 2
            break_candidates = (
                normalized.rfind("\n\n", lower_bound, hard_end),
                normalized.rfind("\n", lower_bound, hard_end),
                normalized.rfind(". ", lower_bound, hard_end),
                normalized.rfind(" ", lower_bound, hard_end),
            )
            best_break = max(break_candidates)
            if best_break > start:
                end = best_break + (2 if normalized[best_break : best_break + 2] == ". " else 0)

        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= length:
            break

        next_start = max(0, end - overlap_chars)
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks
