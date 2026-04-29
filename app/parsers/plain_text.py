def parse_txt(text: str, target_chars: int = 2000) -> list[list[str]]:
    """
    Returns a list of pages, where each page is a list of paragraphs.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    paragraphs = [
        " ".join(p.split())
        for p in text.split("\n\n")
        if p.strip()
    ]

    return _group_into_pages(paragraphs, target_chars)


def _group_into_pages(paragraphs: list[str], target_chars: int) -> list[list[str]]:
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