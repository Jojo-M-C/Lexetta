def group_into_pages(paragraphs: list[str], target_chars: int) -> list[list[str]]:
    """
    Greedily packs paragraphs into pages of roughly target_chars each.
    A page always holds at least one paragraph, even if it overflows.
    """
    pages: list[list[str]] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > target_chars and current:
            pages.append(current)
            current = []
            current_len = 0
        current.append(para)
        current_len += len(para)

    if current:
        pages.append(current)

    return pages
