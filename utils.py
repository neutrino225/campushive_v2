import re


def normalize_university_query(query: str) -> str:
    """Normalize university name and degree acronyms in a case-insensitive, order-aware way.

    Handles common variants like: "FAST-NUCES", "FAST NUCES", "FAST University", "FAST", "NUCES", and "NU".
    Also expands degree shorthand like BS/MS to canonical forms to help retrieval.
    """

    if not query:
        return query

    replacements: list[tuple[str, str]] = [
        (r"\bFAST[-\s]?NUCES\b", "National University of Computer and Emerging Sciences"),
        (r"\bFAST\s+University\b", "National University of Computer and Emerging Sciences"),
        (r"\bNUCES\b", "National University of Computer and Emerging Sciences"),
        (r"\bFAST\b", "National University of Computer and Emerging Sciences"),
        (r"\bNU\b", "National University of Computer and Emerging Sciences"),
        (r"\bBS\b", "Undergraduate"),
        (r"\bMS\b", "Masters"),
    ]

    normalized = query
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)

    return normalized


__all__ = ["normalize_university_query"]
