"""Shared name-tokenization utility for search-token generation.

Generates a ``nameTokens`` list for each product so that Algolia (or any
full-text search engine) can match on exact word boundaries instead of
substring contains.  This dramatically improves relevance – e.g. a search
for "Milch" will rank "Milch 3.5%" higher than "Milchschokolade".
"""

import re

# Minimum token length – single-character tokens are too noisy.
_MIN_TOKEN_LENGTH = 2


def tokenize_name(name: str | None) -> list[str]:
    """Split a product name into deduplicated, lowercase search tokens.

    The function:
    1. Lowercases the input.
    2. Splits on non-letter / non-digit boundaries (keeps umlauts ä ö ü ß).
    3. Drops tokens shorter than ``_MIN_TOKEN_LENGTH`` characters.
    4. Deduplicates while preserving order.

    Examples::

        >>> tokenize_name("Milch 3.5% 1L")
        ['milch']
        >>> tokenize_name("Milchschokolade Vollmilch 100g")
        ['milchschokolade', 'vollmilch', '100g']
        >>> tokenize_name("Ja! Natürlich Bio-Vollmilch")
        ['ja', 'natürlich', 'bio', 'vollmilch']
        >>> tokenize_name(None)
        []
        >>> tokenize_name("")
        []
    """
    if not name:
        return []

    lowered = name.lower()
    # Split on anything that is NOT a letter, digit, or German umlaut/ß.
    tokens = re.findall(r"[a-zäöüß\d]+", lowered)
    # Filter short tokens and deduplicate (preserving order).
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if len(token) >= _MIN_TOKEN_LENGTH and token not in seen:
            seen.add(token)
            result.append(token)
    return result
