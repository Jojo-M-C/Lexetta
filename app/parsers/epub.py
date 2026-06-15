import io
import posixpath
from dataclasses import dataclass, field

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from app.parsers._paging import group_into_pages

# Block-level tags whose text becomes a reading paragraph. Image tags whose
# presence becomes a positioned image marker. Everything else is ignored, so
# decorative wrappers, scripts, and styling never reach the reader.
_TEXT_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote")
_IMAGE_TAGS = ("img", "image")


@dataclass
class EpubImage:
    href: str                    # manifest-absolute path of the image inside the zip
    alt: str | None
    after_paragraph_index: int   # page-local paragraph it follows; -1 = top of page


@dataclass
class EpubPage:
    paragraphs: list[str]
    images: list[EpubImage] = field(default_factory=list)


@dataclass
class EpubChapter:
    title: str
    pages: list[EpubPage]


def parse_epub(raw: bytes, target_chars: int = 3500) -> list[EpubChapter]:
    """
    Extracts an EPUB into ordered chapters, each paginated into pages of
    roughly target_chars. Pages never cross a chapter boundary, so the reader's
    table of contents can jump straight to a chapter's first page. Images are
    recorded with the paragraph they follow, not extracted to disk.
    """
    book = epub.read_epub(io.BytesIO(raw))
    href_titles = _toc_titles(book)
    fallback_title = _book_title(book)

    chapters: list[EpubChapter] = []
    pending_paragraphs: list[str] = []
    pending_images: list[EpubImage] = []
    current_title: str | None = None

    def flush() -> None:
        nonlocal pending_paragraphs, pending_images
        if not pending_paragraphs and not pending_images:
            return
        title = current_title or fallback_title
        chapters.append(EpubChapter(
            title=title,
            pages=_paginate(pending_paragraphs, pending_images, target_chars),
        ))
        pending_paragraphs = []
        pending_images = []

    for item in _spine_documents(book):
        # A spine item listed in the table of contents starts a new chapter;
        # otherwise its content continues the chapter already in progress.
        item_title = href_titles.get(item.file_name)
        if item_title is not None:
            flush()
            current_title = item_title

        base_dir = posixpath.dirname(item.file_name)
        paragraphs, images = _extract_blocks(item.get_content(), base_dir, len(pending_paragraphs))
        pending_paragraphs.extend(paragraphs)
        pending_images.extend(images)

    flush()
    return chapters


def _spine_documents(book: epub.EpubBook):
    """Yields document items in spine (reading) order, skipping the navigation
    document (its content is just the table-of-contents link list, not text)."""
    for entry in book.spine:
        idref = entry[0] if isinstance(entry, (tuple, list)) else entry
        item = book.get_item_with_id(idref)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        if isinstance(item, epub.EpubNav) or "nav" in (getattr(item, "properties", None) or []):
            continue
        yield item


def _toc_titles(book: epub.EpubBook) -> dict[str, str]:
    """Flattens the (possibly nested) table of contents into file_name -> title,
    dropping in-file anchors so a chapter maps to its document."""
    titles: dict[str, str] = {}

    def walk(entries) -> None:
        for entry in entries:
            if isinstance(entry, tuple):  # (Section/Link, [children])
                link, children = entry
                _record(link, titles)
                walk(children)
            else:
                _record(entry, titles)

    walk(book.toc)
    return titles


def _record(link, titles: dict[str, str]) -> None:
    href = getattr(link, "href", None)
    title = getattr(link, "title", None)
    if not href or not title:
        return
    file_name = href.split("#", 1)[0]
    titles.setdefault(file_name, title.strip())


def _book_title(book: epub.EpubBook) -> str:
    meta = book.get_metadata("DC", "title")
    if meta and meta[0] and meta[0][0]:
        return meta[0][0].strip()
    return "Untitled"


def _extract_blocks(
    content: bytes, base_dir: str, start_index: int
) -> tuple[list[str], list[EpubImage]]:
    """Walks one XHTML document in order, returning its text paragraphs and the
    images between them. start_index is the running paragraph count so image
    positions stay correct as documents accumulate into a chapter."""
    soup = BeautifulSoup(content, "html.parser")
    body = soup.body or soup

    paragraphs: list[str] = []
    images: list[EpubImage] = []
    index = start_index

    for el in body.find_all(_TEXT_TAGS + _IMAGE_TAGS):
        if el.name in _IMAGE_TAGS:
            src = el.get("src") or el.get("xlink:href") or el.get("href")
            if not src:
                continue
            images.append(EpubImage(
                href=_resolve(base_dir, src),
                alt=(el.get("alt") or None),
                after_paragraph_index=index - 1,
            ))
        else:
            text = " ".join(el.get_text().split())
            if text:
                paragraphs.append(text)
                index += 1

    return paragraphs, images


def _resolve(base_dir: str, src: str) -> str:
    """Resolves an image src (relative to its XHTML file) to a manifest-absolute
    path matching the zip member name."""
    joined = posixpath.join(base_dir, src) if base_dir else src
    return posixpath.normpath(joined)


def _paginate(
    paragraphs: list[str], images: list[EpubImage], target_chars: int
) -> list[EpubPage]:
    """Splits a chapter's paragraphs into pages and places each image on the page
    holding the paragraph it follows, re-indexed to that page."""
    page_lists = group_into_pages(paragraphs, target_chars)

    # A chapter that is only an image (no text) still needs one page to show it.
    if not page_lists:
        page_lists = [[]]

    pages = [EpubPage(paragraphs=p) for p in page_lists]

    # Map each chapter-global paragraph index to (page, page-local index).
    location: dict[int, tuple[int, int]] = {}
    global_i = 0
    for page_i, page in enumerate(pages):
        for local_i in range(len(page.paragraphs)):
            location[global_i] = (page_i, local_i)
            global_i += 1

    for img in images:
        if img.after_paragraph_index < 0 or img.after_paragraph_index not in location:
            # Before the first paragraph, or trailing past the last one: pin to
            # the top of the first page / bottom of the last page respectively.
            if img.after_paragraph_index < 0:
                pages[0].images.append(EpubImage(img.href, img.alt, -1))
            else:
                last = pages[-1]
                last.images.append(EpubImage(img.href, img.alt, len(last.paragraphs) - 1))
            continue
        page_i, local_i = location[img.after_paragraph_index]
        pages[page_i].images.append(EpubImage(img.href, img.alt, local_i))

    return pages
