from app.parsers._paging import group_into_pages


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

    return group_into_pages(paragraphs, target_chars)
