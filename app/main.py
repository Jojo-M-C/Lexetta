from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
from app.lib.difficulty import LEVEL_ORDER, MLServiceUnavailable, difficult_words, difficult_words_ml, _get_user_history
from app.database import get_db, SessionLocal
from app.models import User, Document, Page, Paragraph, Chapter, EpubImage, ReadWord, HighlightedWord, VocabularyEntry, CalibrationItem, CalibrationResponse
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
from app.lib.sentences import find_sentence, split_sentences_many, map_words_to_sentences
from app.lib.tokenize import word_tokenize
from app.lib.token_filter import predictable_tokens
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
        # Store lowercased: the ML path yields original-case surface forms, while
        # /lookups and the translation cache look rows up by word.lower(). Mixed
        # case here means a capitalised highlight never matches its own lookup.
        key = word.lower()
        if key in existing:
            continue
        existing.add(key)  # two surface cases in one batch must not both insert
        context = next(
            (find_sentence(p.text, word) for p in paragraphs
             if re.search(r'\b' + re.escape(word) + r'\b', p.text, re.IGNORECASE)),
            "",
        )
        # Readers stream highlights in while the user clicks, so this insert races
        # the identical one in /lookups. The row's content is the same either way;
        # whoever gets there first wins.
        db.execute(
            pg_insert(HighlightedWord)
            .values(
                user_id=user.id,
                document_id=document_id,
                page_number=page_number,
                word=key,
                context=context,
                mode=mode,
            )
            .on_conflict_do_nothing(constraint="uq_highlighted_user_doc_page_word")
        )


def _word_is_difficult(
    word: str, sentence: str, user: User, db: Session, displayed: bool
) -> bool:
    """
    Whether the system considers `word` difficult in `sentence`.

    Called from /lookups when no highlight row exists yet. Readers stream
    highlights in chunk by chunk over several seconds, so a word clicked early
    would otherwise be logged as "not highlighted" purely because its chunk had
    not come back — mislabelling the training data the lookup log exists to
    produce. Scoring on demand makes the label independent of click timing.

    If the model is unreachable, fall back to what the reader actually displayed
    rather than failing the lookup.
    """
    if not user.highlighting_enabled:
        return False
    # A name/URL/etc. is never highlighted, so a click on one is "not difficult" —
    # same filter the proactive highlighter uses, applied to the word's sentence.
    if word.lower() not in {t.lower() for t in predictable_tokens(sentence)}:
        return False
    if not user.use_ml_predictions:
        return word.lower() in difficult_words([word], user, db)
    try:
        history = _get_user_history(user, db)
        return word in difficult_words_ml([sentence], [word], history)
    except Exception as e:
        print(f"[lcp] difficulty check failed during lookup: {e}")
        return displayed

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

    # Return the pooled connection during the blocking OpenAI call — the translate
    # step needs no database, and the insert below reacquires one. Rolling back is
    # safe: only the read above is pending. See notes/multi_user_performance.md §3.
    db.rollback()

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


def _prefetch_translations(items: list["PrefetchItem"], user_id: int, mode: str, target_language: str) -> None:
    # One background task per prefetch request (not per word): a single session is
    # reused for every word, so a page's prefetching holds one connection at a time
    # instead of one per word. See notes/multi_user_performance.md §3.
    db = SessionLocal()
    try:
        for item in items:
            try:
                paragraph = db.get(Paragraph, item.paragraph_id)
                if not paragraph:
                    continue
                page = db.get(Page, paragraph.page_id)
                if not page:
                    continue
                document = db.get(Document, page.document_id)
                if not document or document.user_id != user_id:
                    continue

                sentence = find_sentence(paragraph.text, item.word)
                _store_prefetched_translation(
                    db, user_id, document.id, page.page_number, item.word, sentence, mode, target_language
                )
            except Exception as e:
                print(f"Prefetch item error: {e}")
    finally:
        db.close()


def _prefetch_translations_pdf(
    document_id: int,
    page_number: int,
    page_text: str,
    words: list[str],
    user_id: int,
    mode: str,
    target_language: str,
) -> None:
    # PDF counterpart to _prefetch_translations: PDFs have no paragraph rows, so the
    # page text comes from the client (already extracted) rather than the DB.
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if not document or document.user_id != user_id:
            return
        for word in words:
            try:
                sentence = find_sentence(page_text, word)
                _store_prefetched_translation(
                    db, user_id, document_id, page_number, word, sentence, mode, target_language
                )
            except Exception as e:
                print(f"PDF prefetch item error: {e}")
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


class UserCreate(BaseModel):
    username: str

@app.post("/users", status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    """
    Create a survey participant. Only guarded by the shared basic_auth password
    Caddy puts in front of the whole site — enough for a supervised study, where
    the point is creating an account in one curl while the participant waits.

    The new user starts with no reading_level and no target_language, so they
    land on onboarding at first login, and with ML predictions on: survey
    participants are here to exercise the model, unlike the seeded learner_*
    users (which keep the column's CEFR default).
    """
    username = payload.username.strip()
    if not username:
        raise HTTPException(422, "Username must not be empty")
    if len(username) > 64:  # matches the String(64) column
        raise HTTPException(422, "Username must be at most 64 characters")
    # username is UNIQUE; report the clash instead of letting the insert 500.
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(409, "Username already taken")
    user = User(username=username, use_ml_predictions=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


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
    reading_level: str | None = None

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
    if payload.reading_level is not None:
        # Unlike the target language, the reading level stays editable: a learner
        # progresses, and the level drives which words get highlighted.
        if payload.reading_level not in LEVEL_ORDER:
            raise HTTPException(422, "Unknown reading level")
        current_user.reading_level = payload.reading_level
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
    db.commit()

    # Highlighting is deliberately NOT computed here: the ML model takes seconds,
    # and blocking this response on it would mean the reader shows nothing at all
    # until it finishes. The reader renders this text immediately and then streams
    # highlights in via /difficulty, a couple of sentences at a time.
    return {
        "document_id": document_id,
        "title": document.title,
        "page_number": page_number,
        "total_pages": total_pages,
        "paragraphs": [{"id": p.id, "text": p.text} for p in paragraphs],
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
    background_tasks.add_task(_prefetch_translations, payload.words, current_user.id, mode, target_language)
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
    background_tasks.add_task(
        _prefetch_translations_pdf,
        payload.document_id,
        payload.page_number,
        payload.page_text,
        payload.words,
        current_user.id,
        mode,
        target_language,
    )
    return {"queued": len(payload.words)}

class LookupCreate(BaseModel):
    word: str
    # What the reader actually had highlighted on screen. Only a fallback: the
    # logged value is decided server-side, because highlights stream in and an
    # early click would otherwise be recorded as "not highlighted".
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

    # The highlight row for this word on this page, if the reader's difficulty
    # stream has already reached it. It also doubles as the translation cache,
    # keyed by document + page + word, warmed by the prefetch endpoint.
    highlighted = None
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

    # Decided here, never taken from the client: see _word_is_difficult.
    was_highlighted = (
        True if highlighted is not None
        else _word_is_difficult(
            payload.word, sentence, current_user, db, displayed=payload.was_highlighted
        )
    )

    translation_text: str | None = highlighted.translation_target if highlighted else None
    if translation_text is None:
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

    # A word clicked before its chunk was scored (or on a page the reader left
    # early) still belongs in the highlight log, so the log doesn't depend on how
    # long someone stayed on the page. A /difficulty chunk may be inserting the
    # same row right now, hence the conflict-safe insert followed by a re-select.
    if highlighted is None and was_highlighted and page_number is not None:
        db.execute(
            pg_insert(HighlightedWord)
            .values(
                user_id=current_user.id,
                document_id=document.id,
                page_number=page_number,
                word=payload.word.lower(),
                context=sentence,
                mode=mode,
            )
            .on_conflict_do_nothing(constraint="uq_highlighted_user_doc_page_word")
        )
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
        # Backfill the cache if a live lookup beat the prefetch task to it.
        if highlighted.translation_target is None and translation_text is not None:
            highlighted.translation_target = translation_text

    # Record the click as verified training data. Upsert on (user, doc, page, word):
    # the page-read commit may already have inserted this word as a negative, or a
    # later commit may run after this click — either way was_clicked stays True.
    highlighted_id = highlighted.id if highlighted is not None else None
    # The model behind this row: the highlight's mode if it was flagged, otherwise
    # the mode active for this user (which chose not to flag it).
    read_mode = highlighted.mode if highlighted is not None else mode
    read_row = None
    if page_number is not None:
        read_stmt = (
            pg_insert(ReadWord)
            .values(
                user_id=current_user.id,
                document_id=document.id,
                paragraph_id=paragraph.id if paragraph else None,
                page_number=page_number,
                word=payload.word.lower(),
                context=clicked_context,
                was_clicked=True,
                was_highlighted=highlighted is not None,
                highlighted_word_id=highlighted_id,
                mode=read_mode,
            )
            .on_conflict_do_update(
                constraint="uq_read_user_doc_page_word",
                set_={
                    "was_clicked": True,
                    "was_highlighted": ReadWord.was_highlighted | (highlighted is not None),
                    "highlighted_word_id": func.coalesce(
                        ReadWord.highlighted_word_id, highlighted_id
                    ),
                    "mode": read_mode,
                },
            )
            .returning(ReadWord.id, ReadWord.created_at)
        )
        read_row = db.execute(read_stmt).first()

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

    return {
        "id": read_row.id if read_row else None,
        "occurred_at": read_row.created_at if read_row else None,
        "word": payload.word,
        "translation": (
            {"target": translation_text, "source": payload.word}
            if translation_text else None
        ),
    }

class PageReadRequest(BaseModel):
    document_id: int
    page_number: int
    # Required for pdf (no paragraph rows exist); ignored for txt/epub, whose text
    # is read from the stored paragraph rows.
    page_text: str | None = None


@app.post("/pages/read", status_code=201)
def mark_page_read(
    payload: PageReadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Commit a page the reader demonstrably read (dwell time crossed a threshold)
    into read_words: every word on the page becomes a labelled training example.

    was_highlighted mirrors the highlighted_words log for the page. was_clicked is
    left to the click path — an existing clicked row is never downgraded, and words
    not yet present are inserted as negatives (was_clicked=False by default)."""
    document = db.get(Document, payload.document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(404, "Document not found")

    # Build (word_lower -> paragraph_id, context) for every distinct word on the
    # page. txt/epub read from paragraph rows; pdf tokenises the supplied page text.
    rows: dict[str, tuple[int | None, str]] = {}
    if document.source_format in ("txt", "epub"):
        page = (
            db.query(Page)
            .filter(Page.document_id == document.id, Page.page_number == payload.page_number)
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
        for paragraph in paragraphs:
            for token in word_tokenize(paragraph.text):
                key = token.lower()
                # First occurrence wins: keep its paragraph and paragraph text as context.
                rows.setdefault(key, (paragraph.id, paragraph.text))
    else:  # pdf
        if payload.page_text is None:
            raise HTTPException(422, "page_text is required for pdf documents")
        words = list({t.lower() for t in word_tokenize(payload.page_text)})
        sentences = map_words_to_sentences(payload.page_text, words)
        for key in words:
            rows[key] = (None, sentences[key])

    if not rows:
        return {"counted": 0}

    # What the system highlighted on this page — the source of truth for
    # was_highlighted, the link target for highlighted_word_id, and the mode of
    # each positive. word -> (highlight id, highlight mode).
    highlighted = {
        row.word: (row.id, row.mode)
        for row in db.query(HighlightedWord.word, HighlightedWord.id, HighlightedWord.mode).filter(
            HighlightedWord.user_id == current_user.id,
            HighlightedWord.document_id == document.id,
            HighlightedWord.page_number == payload.page_number,
        )
    }

    # The mode active for this user, used for words not highlighted on this page
    # (the model that saw them and did not flag them).
    active_mode = "ml" if current_user.use_ml_predictions else "cefr"

    values = [
        {
            "user_id": current_user.id,
            "document_id": document.id,
            "paragraph_id": paragraph_id,
            "page_number": payload.page_number,
            "word": word,
            "context": context,
            "was_highlighted": word in highlighted,
            "highlighted_word_id": highlighted[word][0] if word in highlighted else None,
            "mode": highlighted[word][1] if word in highlighted else active_mode,
        }
        for word, (paragraph_id, context) in rows.items()
    ]

    stmt = pg_insert(ReadWord).values(values)
    db.execute(
        stmt.on_conflict_do_update(
            constraint="uq_read_user_doc_page_word",
            set_={
                # was_clicked is deliberately absent: never overwrite a click.
                "was_highlighted": stmt.excluded.was_highlighted,
                "highlighted_word_id": stmt.excluded.highlighted_word_id,
                "context": stmt.excluded.context,
                "paragraph_id": stmt.excluded.paragraph_id,
                "mode": stmt.excluded.mode,
            },
        )
    )
    db.commit()

    return {"counted": len(values)}


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
    # Arbitrary blocks of text (paragraphs, sentences, a PDF page). The server
    # segments them, so each token is scored in its own sentence rather than in
    # whatever block the caller happened to send.
    texts: list[str]
    # Set by the txt/epub readers so ML highlights can be logged as research data.
    # PDFs have no page/paragraph rows and send neither, so nothing is stored.
    document_id: int | None = None
    page_number: int | None = None
    # Lowercased word types the caller already had scored for this page. Highlights
    # are decided per word type, not per occurrence, so re-scoring these would be
    # discarded work. Readers stream a page in chunks and accumulate this list.
    exclude: list[str] = []


def _page_paragraphs(db: Session, document_id: int, page_number: int) -> list[Paragraph]:
    """Paragraph rows for a page, or [] for formats that have none (pdf)."""
    page = (
        db.query(Page)
        .filter(Page.document_id == document_id, Page.page_number == page_number)
        .first()
    )
    if not page:
        return []
    return (
        db.query(Paragraph)
        .filter(Paragraph.page_id == page.id)
        .order_by(Paragraph.paragraph_index)
        .all()
    )


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

    # Authorise before spending GPU time, not after.
    if payload.document_id is not None:
        document = db.get(Document, payload.document_id)
        if not document or document.user_id != current_user.id:
            raise HTTPException(404, "Document not found")

    # Score each word type at most once per page. Both difficulty functions return
    # a set of words, so a repeated occurrence can only produce a duplicate answer
    # at full cost. The trade: the first occurrence's sentence is the context that
    # decides the word, instead of "difficult if any occurrence scores high".
    seen: set[str] = {word.lower() for word in payload.exclude}

    if current_user.use_ml_predictions:
        # The model scores each token in its own sentence, so build parallel
        # sentence/token lists rather than passing the caller's blocks through.
        sentences: list[str] = []
        words: list[str] = []
        for block_sentences in split_sentences_many(payload.texts):
            for sentence in block_sentences:
                for word in predictable_tokens(sentence):
                    if word.lower() in seen:
                        continue
                    seen.add(word.lower())
                    sentences.append(sentence)
                    words.append(word)
        try:
            history = _get_user_history(current_user, db)
            # Release the pooled connection during the multi-second remote GPU call:
            # nothing below needs the DB until the highlight-persist step, and holding
            # a connection across the remote call is what saturated the pool under a
            # few concurrent readers. See notes/multi_user_performance.md §3/§5.
            db.commit()
            difficult = difficult_words_ml(sentences, words, history)
        except MLServiceUnavailable as e:
            # No CEFR fallback: the reader shows an outage banner and no highlights,
            # rather than silently mixing rule-based highlights into an ML session.
            print(f"[lcp] difficulty unavailable: {e}")
            raise HTTPException(503, "Difficulty model is unavailable") from e
    else:
        words = []
        for text in payload.texts:
            for word in predictable_tokens(text):
                if word.lower() in seen:
                    continue
                seen.add(word.lower())
                words.append(word)
        difficult = difficult_words(words, current_user, db)

    # Only ML highlights are logged, and only for formats with paragraph rows —
    # matching what get_page used to do before highlighting moved here.
    if difficult and current_user.use_ml_predictions and payload.document_id is not None \
            and payload.page_number is not None:
        paragraphs = _page_paragraphs(db, payload.document_id, payload.page_number)
        if paragraphs:
            _persist_highlighted_words(
                db, current_user, payload.document_id, payload.page_number,
                difficult, paragraphs, mode="ml",
            )
            db.commit()

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
    # SET NULL: read_words.document_id and .paragraph_id become NULL,
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