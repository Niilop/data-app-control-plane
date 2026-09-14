"""Deterministic synthetic batch; no external data or services."""


def summarize(count: int) -> dict[str, int]:
    if not 1 <= count <= 10000:
        raise ValueError("count must be between 1 and 10000")
    return {"rows": count, "total": sum(range(count))}
