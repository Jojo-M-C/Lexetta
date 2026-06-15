from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from app.lib.difficulty import difficult_words, difficult_words_ml
from app.database import get_db, SessionLocal
from app.models import User, Document, Page, Paragraph, Chapter, EpubImage, ClickedWord, HighlightedWord, VocabularyEntry, CalibrationItem, CalibrationResponse
from pydantic import BaseModel
import random
import re
import uuid
from pathlib import Path
from app.config import settings
from app.parsers.plain_text import parse_txt
from app.parsers.epub import parse_epub, EpubChapter
import zipfile
import mimetypes
import posixpath
from app.lib.translators.factory import get_translator
from app.lib.languages import TARGET_LANGUAGES, DEFAULT_LANGUAGE
from app.lib.sentences import find_sentence, split_sentences
from app.lib.tokenize import word_tokenize
import csv
import io
import os
import pdfplumber
from datetime import date
from fastapi.responses import StreamingResponse

# pdfplumber.extract_words() starts a new word when the gap between characters
# exceeds x_tolerance. Justified PDFs often have word gaps (~2.5pt) narrower than
# the 3pt default, so whole lines collapse into one token — which would produce
# line-spanning highlights. 2pt sits between the within-word (~0pt) and
# between-word gaps, splitting words correctly without breaking them apart.
_PDF_WORD_X_TOLERANCE = 2


def _persist_highlighted_words(
    db: Session,
    user: User,
    document_id: int,
    page_number: int,
    words: set[str],
    paragraphs: list[Paragraph],
    mode: str,
) -> None:
    existing = {
        row.word for row in
        db.query(HighlightedWord.word).filter(
            HighlightedWord.user_id == user.id,
            HighlightedWord.document_id == document_id,
            HighlightedWord.page_number == page_number,
        ).all()
    }

    for word in words:
        if word in existing:
            continue
        context = next(
            (find_sentence(p.text, word) for p in paragraphs
             if re.search(r'\b' + re.escape(word) + r'\b', p.text, re.IGNORECASE)),
            "",
        )
        db.add(HighlightedWord(
            user_id=user.id,
            document_id=document_id,
            page_number=page_number,
            word=word,
            context=context,
            mode=mode,
        ))

def _store_prefetched_translation(
    db: Session,
    user_id: int,
    document_id: int,
    page_number: int,
    word: str,
    sentence: str,
    mode: str,
    target_language: str,
) -> None:
    """Translate `word` (in `sentence`) and cache it on the
    (user, document, page, word) HighlightedWord row, creating the row if needed.

    Uses INSERT ... ON CONFLICT so a concurrent prefetch of the same word — e.g.
    navigating back to a page before its first prefetch finished — fills in the
    translation instead of colliding on the unique constraint.
    """
    word_lower = word.lower()

    existing = (
        db.query(HighlightedWord)
        .filter(
            HighlightedWord.user_id == user_id,
            HighlightedWord.document_id == document_id,
            HighlightedWord.page_number == page_number,
            HighlightedWord.word == word_lower,
        )
        .first()
    )
    if existing and existing.translation_target:
        return  # already cached — no need to call the translator again

    translation: str | None = None
    try:
        result = get_translator().translate(word, context=sentence, target_lang=target_language)
        if result:
            translation = result.target
    except Exception as e:
        print(f"Prefetch translation error for '{word}': {e}")

    stmt = (
        pg_insert(HighlightedWord)
        .values(
            user_id=user_id,
            document_id=document_id,
            page_number=page_number,
            word=word_lower,
            context=sentence,
            mode=mode,
            translation_target=translation,
        )
        .on_conflict_do_update(
            constraint="uq_highlighted_user_doc_page_word",
            set_={"translation_target": translation},
            where=HighlightedWord.translation_target.is_(None),
        )
    )
    db.execute(stmt)
    db.commit()


def _prefetch_translation(paragraph_id: int, word: str, user_id: int, mode: str, target_language: str) -> None:
    db = SessionLocal()
    try:
        paragraph = db.get(Paragraph, paragraph_id)
        if not paragraph:
            return
        page = db.get(Page, paragraph.page_id)
        if not page:
            return
        document = db.get(Document, page.document_id)
        if not document or document.user_id != user_id:
            return

        sentence = find_sentence(paragraph.text, word)
        _store_prefetched_translation(
            db, user_id, document.id, page.page_number, word, sentence, mode, target_language
        )
    except Exception as e:
        print(f"Prefetch task error: {e}")
    finally:
        db.close()


def _prefetch_translation_pdf(
    document_id: int,
    page_number: int,
    word: str,
    page_text: str,
    user_id: int,
    mode: str,
    target_language: str,
) -> None:
    # PDF counterpart to _prefetch_translation: PDFs have no paragraph rows, so
    # the page text comes from the client (already extracted) rather than the DB.
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if not document or document.user_id != user_id:
            return

        sentence = find_sentence(page_text, word)
        _store_prefetched_translation(
            db, user_id, document_id, page_number, word, sentence, mode, target_language
        )
    except Exception as e:
        print(f"PDF prefetch task error: {e}")
    finally:
        db.close()

app = FastAPI(title="Lexetta")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "connected"}


def get_current_user(
    x_user_id: int = Header(...),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, x_user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    return db.query(User).order_by(User.id).all()


@app.get("/languages")
def list_languages():
    # Public: feeds the onboarding language dropdown. Sorted by display name.
    return [
        {"code": code, "name": name}
        for code, name in sorted(TARGET_LANGUAGES.items(), key=lambda kv: kv[1])
    ]


@app.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return current_user

class UserSettingsUpdate(BaseModel):
    use_ml_predictions: bool | None = None
    highlighting_enabled: bool | None = None

@app.patch("/users/me")
def update_me(
    payload: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.use_ml_predictions is not None:
        current_user.use_ml_predictions = payload.use_ml_predictions
    if payload.highlighting_enabled is not None:
        current_user.highlighting_enabled = payload.highlighting_enabled
    db.commit()
    db.refresh(current_user)
    return current_user


class LanguageSelect(BaseModel):
    target_language: str

@app.post("/users/me/language")
def set_target_language(
    payload: LanguageSelect,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # The target language is chosen once at onboarding and then fixed, so reject
    # any attempt to change it after it's been set.
    if current_user.target_language is not None:
        raise HTTPException(409, "Target language is already set and cannot be changed")
    if payload.target_language not in TARGET_LANGUAGES:
        raise HTTPException(422, "Unknown target language")
    current_user.target_language = payload.target_language
    db.commit()
    db.refresh(current_user)
    return current_user

@app.get("/calibration/words")
def get_calibration_words(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = db.query(CalibrationItem).all()
    random.shuffle(items)
    return [{"id": i.id, "word": i.word, "sentence": i.sentence} for i in items]


class CalibrationRating(BaseModel):
    item_id: int
    difficulty_rating: int  # 1–5

class CalibrationSubmit(BaseModel):
    ratings: list[CalibrationRating]

@app.post("/calibration", status_code=201)
def submit_calibration(
    payload: CalibrationSubmit,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    for r in payload.ratings:
        if not 1 <= r.difficulty_rating <= 5:
            raise HTTPException(400, f"difficulty_rating must be 1–5, got {r.difficulty_rating}")
        db.add(CalibrationResponse(
            user_id=current_user.id,
            item_id=r.item_id,
            difficulty_rating=r.difficulty_rating,
        ))
    current_user.calibration_done = True
    db.commit()
    return {"calibration_done": True}


@app.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Validate format
    if not file.filename:
        raise HTTPException(400, "No filename")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("txt", "pdf", "epub"):
        raise HTTPException(400, f"Unsupported format: .{ext} (only .txt, .pdf and .epub)")

    # Read file (PDFs/EPUBs are binary and run larger than plain text)
    raw = await file.read()
    max_mb = 5 if ext == "txt" else 25
    if len(raw) > max_mb * 1024 * 1024:
        raise HTTPException(400, f"File too large (max {max_mb} MB)")

    # Parse/validate content before touching the disk so a bad file leaves nothing
    # behind. txt: split into pages/paragraphs. pdf: confirm it opens and has pages.
    # epub: extract chapters → pages/paragraphs/images.
    pages_data: list[list[str]] | None = None
    epub_chapters: list[EpubChapter] | None = None
    if ext == "txt":
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(400, "File is not valid UTF-8 text")
        pages_data = parse_txt(text)
        if not pages_data:
            raise HTTPException(400, "File appears to be empty")
    elif ext == "epub":
        # EPUB is a ZIP archive (magic bytes "PK\x03\x04").
        if not raw.startswith(b"PK\x03\x04"):
            raise HTTPException(400, "File is not a valid EPUB")
        try:
            epub_chapters = parse_epub(raw)
        except Exception:
            raise HTTPException(400, "Could not read EPUB")
        if not any(pg.paragraphs for ch in epub_chapters for pg in ch.pages):
            raise HTTPException(400, "EPUB has no readable text")
    else:
        if not raw.startswith(b"%PDF-"):
            raise HTTPException(400, "File is not a valid PDF")
        try:
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                pdf_page_count = len(pdf.pages)
        except Exception:
            raise HTTPException(400, "Could not read PDF")
        if pdf_page_count == 0:
            raise HTTPException(400, "PDF has no pages")

    # Save original to disk
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4()}.{ext}"
    file_path = upload_dir / stored_filename
    file_path.write_bytes(raw)

    # Title = filename without extension
    title = file.filename.rsplit(".", 1)[0]

    document = Document(
        user_id=current_user.id,
        title=title,
        source_format=ext,
        original_filename=file.filename,
        file_path=str(file_path),
    )
    db.add(document)
    db.flush()  # assigns document.id without committing

    # txt documents are stored as page/paragraph rows for the HTML reader. PDFs
    # are rendered directly by the frontend (PDF.js + on-demand word boxes), so
    # they need no structural rows. EPUBs add chapter rows and positioned images.
    page_count = 0
    if pages_data is not None:
        for page_idx, paragraphs in enumerate(pages_data, start=1):
            page = Page(document_id=document.id, page_number=page_idx)
            db.add(page)
            db.flush()

            for para_idx, para_text in enumerate(paragraphs):
                db.add(Paragraph(
                    page_id=page.id,
                    paragraph_index=para_idx,
                    text=para_text,
                ))
        page_count = len(pages_data)
    elif epub_chapters is not None:
        # Pages are numbered globally across chapters so the reader's flat
        # pagination still works; each page also links to its chapter for the TOC.
        page_number = 0
        for chapter_index, chapter in enumerate(epub_chapters):
            chapter_row = Chapter(
                document_id=document.id,
                chapter_index=chapter_index,
                title=chapter.title,
            )
            db.add(chapter_row)
            db.flush()

            for epub_page in chapter.pages:
                page_number += 1
                page = Page(
                    document_id=document.id,
                    chapter_id=chapter_row.id,
                    page_number=page_number,
                )
                db.add(page)
                db.flush()

                for para_idx, para_text in enumerate(epub_page.paragraphs):
                    db.add(Paragraph(
                        page_id=page.id,
                        paragraph_index=para_idx,
                        text=para_text,
                    ))
                for img in epub_page.images:
                    db.add(EpubImage(
                        page_id=page.id,
                        href=img.href,
                        alt=img.alt,
                        after_paragraph_index=img.after_paragraph_index,
                    ))
        page_count = page_number
    else:
        page_count = pdf_page_count

    db.commit()
    db.refresh(document)

    return {
        "id": document.id,
        "title": document.title,
        "page_count": page_count,
    }


@app.get("/documents")
def list_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.uploaded_at.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "title": d.title,
            "source_format": d.source_format,
            "uploaded_at": d.uploaded_at,
            "last_page_read": d.last_page_read,
        }
        for d in docs
    ]

@app.get("/documents/{document_id}/pages/{page_number}")
def get_page(
    document_id: int,
    page_number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(404, "Document not found")

    page = (
        db.query(Page)
        .filter(Page.document_id == document_id, Page.page_number == page_number)
        .first()
    )
    if not page:
        raise HTTPException(404, "Page not found")

    paragraphs = (
        db.query(Paragraph)
        .filter(Paragraph.page_id == page.id)
        .order_by(Paragraph.paragraph_index)
        .all()
    )

    total_pages = (
        db.query(Page).filter(Page.document_id == document_id).count()
    )

    # Chapter + images only exist for EPUB pages (chapter_id is set); null/[] otherwise.
    chapter = db.get(Chapter, page.chapter_id) if page.chapter_id else None
    images = (
        db.query(EpubImage)
        .filter(EpubImage.page_id == page.id)
        .order_by(EpubImage.after_paragraph_index)
        .all()
    )

    document.last_page_read = page_number

    ml_highlights: list[str] | None = None
    if current_user.use_ml_predictions and current_user.highlighting_enabled:
        # The ML model scores each token in its sentence context, so build
        # parallel sentence/token lists from the page's paragraphs (same shape
        # the /difficulty endpoint feeds it).
        sentences: list[str] = []
        tokens: list[str] = []
        for para in paragraphs:
            for sentence in split_sentences(para.text):
                for word in word_tokenize(sentence):
                    sentences.append(sentence)
                    tokens.append(word)
        ml_set = difficult_words_ml(sentences, tokens, current_user, db) or set()
        ml_highlights = sorted(ml_set)
        _persist_highlighted_words(db, current_user, document_id, page_number, ml_set, paragraphs, mode="ml")

    db.commit()

    return {
        "document_id": document_id,
        "title": document.title,
        "page_number": page_number,
        "total_pages": total_pages,
        "paragraphs": [{"id": p.id, "text": p.text} for p in paragraphs],
        "ml_highlights": ml_highlights,
        "chapter": (
            {"index": chapter.chapter_index, "title": chapter.title}
            if chapter else None
        ),
        "images": [
            {
                "url": f"/documents/{document_id}/images/{img.href}",
                "alt": img.alt,
                "after_paragraph_index": img.after_paragraph_index,
            }
            for img in images
        ],
    }


@app.get("/documents/{document_id}/chapters")
def get_chapters(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Table of contents: chapters in reading order, each with the page number
    to jump to (its first page). Empty for non-EPUB documents."""
    document = db.get(Document, document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(404, "Document not found")

    chapters = (
        db.query(Chapter)
        .filter(Chapter.document_id == document_id)
        .order_by(Chapter.chapter_index)
        .all()
    )

    result = []
    for chapter in chapters:
        first_page = (
            db.query(Page.page_number)
            .filter(Page.chapter_id == chapter.id)
            .order_by(Page.page_number)
            .first()
        )
        if first_page is None:
            continue
        result.append({
            "index": chapter.chapter_index,
            "title": chapter.title,
            "page_number": first_page[0],
        })

    return {"chapters": result}


@app.get("/documents/{document_id}/images/{href:path}")
def get_document_image(
    document_id: int,
    href: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Streams an image straight out of the stored EPUB zip. Only hrefs recorded
    in epub_images are served, which prevents reading arbitrary zip members or
    traversing out of the archive."""
    document = db.get(Document, document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(404, "Document not found")

    known = (
        db.query(EpubImage)
        .join(Page, EpubImage.page_id == Page.id)
        .filter(Page.document_id == document_id, EpubImage.href == href)
        .first()
    )
    if known is None:
        raise HTTPException(404, "Image not found")

    path = Path(document.file_path)
    if not path.exists():
        raise HTTPException(404, "EPUB file not found on disk")

    try:
        with zipfile.ZipFile(path) as zf:
            # Stored hrefs are relative to the OPF; the zip member also carries the
            # content directory (e.g. "EPUB/"), so resolve it before reading.
            member = posixpath.normpath(posixpath.join(_epub_content_dir(zf), href))
            data = zf.read(member)
    except KeyError:
        raise HTTPException(404, "Image not found in EPUB")

    media_type = mimetypes.guess_type(href)[0] or "application/octet-stream"
    return StreamingResponse(io.BytesIO(data), media_type=media_type)


def _epub_content_dir(zf: zipfile.ZipFile) -> str:
    """Directory of the OPF package inside the EPUB zip, which image hrefs are
    relative to. Read from META-INF/container.xml; '' if the OPF is at the root."""
    container = zf.read("META-INF/container.xml").decode("utf-8")
    match = re.search(r'full-path="([^"]+)"', container)
    if not match:
        return ""
    return posixpath.dirname(match.group(1))

@app.get("/documents/{document_id}/pdf")
def get_document_pdf(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(404, "Document not found")
    if document.source_format != "pdf":
        raise HTTPException(404, "Document is not a PDF")

    path = Path(document.file_path)
    if not path.exists():
        raise HTTPException(404, "PDF file not found on disk")

    def _stream():
        with path.open("rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk

    return StreamingResponse(
        _stream(),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@app.get("/documents/{document_id}/pages/{page_number}/text")
def get_document_page_text(
    document_id: int,
    page_number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(404, "Document not found")
    if document.source_format != "pdf":
        raise HTTPException(404, "Document is not a PDF")

    path = Path(document.file_path)
    if not path.exists():
        raise HTTPException(404, "PDF file not found on disk")

    with pdfplumber.open(path) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            raise HTTPException(404, "Page not found")
        text = pdf.pages[page_number - 1].extract_text(x_tolerance=_PDF_WORD_X_TOLERANCE) or ""

    return {"page": page_number, "text": text}


@app.get("/documents/{document_id}/pages/{page_number}/words")
def get_document_page_words(
    document_id: int,
    page_number: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(404, "Document not found")
    if document.source_format != "pdf":
        raise HTTPException(404, "Document is not a PDF")

    path = Path(document.file_path)
    if not path.exists():
        raise HTTPException(404, "PDF file not found on disk")

    # Per-word bounding boxes in PDF points (top-left origin), so the frontend
    # can overlay pixel-accurate highlights by scaling with the render scale.
    # The text layer alone can't do this: a multi-word text run is a single
    # span whose internal word positions only approximate the embedded font.
    with pdfplumber.open(path) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            raise HTTPException(404, "Page not found")
        page = pdf.pages[page_number - 1]
        words = [
            {
                "text": w["text"],
                "x0": w["x0"],
                "top": w["top"],
                "x1": w["x1"],
                "bottom": w["bottom"],
            }
            for w in page.extract_words(x_tolerance=_PDF_WORD_X_TOLERANCE)
        ]
        text = page.extract_text(x_tolerance=_PDF_WORD_X_TOLERANCE) or ""

    # Remember the reading position, mirroring the txt reader's get_page. The
    # PDF reader fetches this endpoint on every page change, so it's the natural
    # place to persist progress (the Library link reopens at last_page_read).
    document.last_page_read = page_number
    db.commit()

    return {
        "page": page_number,
        "width": float(page.width),
        "height": float(page.height),
        "text": text,
        "words": words,
    }


class PrefetchItem(BaseModel):
    paragraph_id: int
    word: str

class PrefetchRequest(BaseModel):
    words: list[PrefetchItem]

@app.post("/prefetch", status_code=202)
def prefetch_translations(
    payload: PrefetchRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    mode = "ml" if current_user.use_ml_predictions else "cefr"
    target_language = current_user.target_language or DEFAULT_LANGUAGE
    for item in payload.words:
        background_tasks.add_task(_prefetch_translation, item.paragraph_id, item.word, current_user.id, mode, target_language)
    return {"queued": len(payload.words)}


class PdfPrefetchRequest(BaseModel):
    document_id: int
    page_number: int
    page_text: str
    words: list[str]

@app.post("/prefetch/pdf", status_code=202)
def prefetch_pdf_translations(
    payload: PdfPrefetchRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    mode = "ml" if current_user.use_ml_predictions else "cefr"
    target_language = current_user.target_language or DEFAULT_LANGUAGE
    for word in payload.words:
        background_tasks.add_task(
            _prefetch_translation_pdf,
            payload.document_id,
            payload.page_number,
            word,
            payload.page_text,
            current_user.id,
            mode,
            target_language,
        )
    return {"queued": len(payload.words)}

class LookupCreate(BaseModel):
    word: str
    was_highlighted: bool
    paragraph_id: int | None = None
    # PDF documents have no paragraph rows; the frontend instead sends the
    # document id, page number, and extracted page text. page_number keys the
    # translation cache (HighlightedWord) just like the txt reader's pages.
    document_id: int | None = None
    page_number: int | None = None
    page_text: str | None = None

@app.post("/lookups")
def create_lookup(
    payload: LookupCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Resolve the document, the sentence context for translation, and the
    # snapshot text stored on the ClickedWord. Two sources of context:
    #   - txt documents identify a paragraph row (paragraph_id)
    #   - pdf documents send document_id + page_text (no paragraph rows exist)
    page = None
    paragraph = None
    page_number: int | None = None
    mode = "ml" if current_user.use_ml_predictions else "cefr"
    if payload.paragraph_id is not None:
        paragraph = db.get(Paragraph, payload.paragraph_id)
        if not paragraph:
            raise HTTPException(404, "Paragraph not found")
        page = db.get(Page, paragraph.page_id)
        if not page:
            raise HTTPException(404, "Page not found")
        document = db.get(Document, page.document_id)
        if not document or document.user_id != current_user.id:
            raise HTTPException(404, "Document not found")
        sentence = find_sentence(paragraph.text, payload.word)
        clicked_context = paragraph.text
        page_number = page.page_number
    else:
        if payload.document_id is None or payload.page_text is None:
            raise HTTPException(422, "Either paragraph_id or document_id with page_text is required")
        document = db.get(Document, payload.document_id)
        if not document or document.user_id != current_user.id:
            raise HTTPException(404, "Document not found")
        sentence = find_sentence(payload.page_text, payload.word)
        # PDFs have no paragraph rows; store the sentence (not the whole page) so
        # the context stays bounded, like the txt reader's paragraph snapshot.
        clicked_context = sentence
        page_number = payload.page_number

    # Reuse a cached translation when one exists, keyed by document + page + word.
    # Both readers warm difficult words via a prefetch endpoint on page load.
    cached = None
    if page_number is not None:
        cached = (
            db.query(HighlightedWord)
            .filter(
                HighlightedWord.user_id == current_user.id,
                HighlightedWord.document_id == document.id,
                HighlightedWord.page_number == page_number,
                HighlightedWord.word == payload.word.lower(),
                HighlightedWord.translation_target.isnot(None),
            )
            .first()
        )

    translation_text: str | None = None
    if cached:
        translation_text = cached.translation_target
    else:
        try:
            result = get_translator().translate(
                payload.word,
                context=sentence,
                target_lang=current_user.target_language or DEFAULT_LANGUAGE,
            )
            if result:
                translation_text = result.target
        except Exception as e:
            print(f"Translator error: {e}")
    event = ClickedWord(
        user_id=current_user.id,
        document_id=document.id,
        paragraph_id=paragraph.id if paragraph else None,
        word=payload.word,
        context=clicked_context,
        was_highlighted=payload.was_highlighted,
        mode=mode,
    )
    db.add(event)
    db.flush()  # get event.id before using it below

    if page_number is not None:
        highlighted = (
            db.query(HighlightedWord)
            .filter(
                HighlightedWord.user_id == current_user.id,
                HighlightedWord.document_id == document.id,
                HighlightedWord.page_number == page_number,
                HighlightedWord.word == payload.word.lower(),
            )
            .first()
        )
        if highlighted is not None:
            highlighted.was_clicked = True
            highlighted.clicked_word_id = event.id
            # Backfill the cache if a live lookup beat the prefetch task to it.
            if highlighted.translation_target is None and translation_text is not None:
                highlighted.translation_target = translation_text

    # Add a vocabulary card. A card is a word in a specific sentence, so dedup on
    # (word, context): the same word in a new sentence is a new card, but an exact
    # repeat (e.g. double-clicking, or re-reading the same line) isn't duplicated.
    # Deduping on (word, translation) alone was too broad — once a word was carded
    # it could never be added again from any other document or context.
    existing = (
        db.query(VocabularyEntry)
        .filter(
            VocabularyEntry.user_id == current_user.id,
            VocabularyEntry.word == payload.word,
            VocabularyEntry.context == sentence,
        )
        .first()
    )
    if existing is None:
        db.add(VocabularyEntry(
            user_id=current_user.id,
            word=payload.word,
            context=sentence,
            translation=translation_text,
        ))
    elif existing.translation is None and translation_text is not None:
        # Fill in a translation that failed on a previous click.
        existing.translation = translation_text

    db.commit()
    db.refresh(event)

    return {
        "id": event.id,
        "occurred_at": event.occurred_at,
        "word": payload.word,
        "translation": (
            {"target": translation_text, "source": payload.word}
            if translation_text else None
        ),
    }

@app.get("/vocabulary")
def list_vocabulary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entries = (
        db.query(VocabularyEntry)
        .filter(VocabularyEntry.user_id == current_user.id)
        .order_by(VocabularyEntry.created_at.desc())
        .all()
    )
    return [
        {
            "id": e.id,
            "word": e.word,
            "context": e.context,
            "translation": e.translation,
            "created_at": e.created_at,
        }
        for e in entries
    ]

@app.delete("/vocabulary/{entry_id}")
def delete_vocabulary(
    entry_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entry = db.get(VocabularyEntry, entry_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(404, "Vocabulary entry not found")
    db.delete(entry)
    db.commit()
    return {"id": entry_id, "deleted": True}

class DifficultyRequest(BaseModel):
    sentences: list[str]

@app.post("/difficulty")
def get_difficulty(
    payload: DifficultyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # When the user has turned proactive highlighting off, nothing is flagged
    # difficult — they can still click any word to look it up.
    if not current_user.highlighting_enabled:
        return {"difficult": []}
    
    sentences: list[str] = []
    words: list[str] = []
    for sentence in payload.sentences:
        for word in word_tokenize(sentence):
            sentences.append(sentence)
            words.append(word)
    difficult = difficult_words_ml(sentences, words, current_user, db)
    return {"difficult": sorted(difficult)}
@app.get("/vocabulary/export")
def export_vocabulary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    entries = (
        db.query(VocabularyEntry)
        .filter(
            VocabularyEntry.user_id == current_user.id,
            VocabularyEntry.translation.is_not(None),
        )
        .order_by(VocabularyEntry.created_at.desc())
        .all()
    )

    output = io.StringIO()
    # Tab-separated, no header (Anki imports raw rows by default)
    writer = csv.writer(output, delimiter="\t", quoting=csv.QUOTE_MINIMAL)

    for entry in entries:
        front = f'{entry.word}\n"{entry.context}"'
        back = entry.translation
        writer.writerow([front, back])

    output.seek(0)
    today = date.today().isoformat()
    filename = f"lexetta_vocab_{today}.tsv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/tab-separated-values",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )

@app.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(404, "Document not found")

    # Capture file path before the row goes
    file_path = document.file_path

    # Delete the database row.
    # Cascades: pages, paragraphs (via pages) cascade-delete.
    # SET NULL: clicked_words.document_id and .paragraph_id become NULL,
    # so the research data persists.
    db.delete(document)
    db.commit()

    # Best-effort filesystem cleanup. Don't fail the request if this errors —
    # the database state is already consistent and the file is just orphaned.
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
    except OSError as e:
        print(f"Failed to delete file {file_path}: {e}")

    return {"id": document_id, "deleted": True}


class DocumentRename(BaseModel):
    title: str


@app.patch("/documents/{document_id}")
def rename_document(
    document_id: int,
    payload: DocumentRename,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(404, "Document not found")

    title = payload.title.strip()
    if not title:
        raise HTTPException(400, "Title cannot be empty")
    if len(title) > 255:  # matches Document.title column length
        raise HTTPException(400, "Title is too long (max 255 characters)")

    document.title = title
    db.commit()

    return {"id": document.id, "title": document.title}