from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.lib.difficulty import difficult_words, difficult_words_ml
from app.database import get_db, SessionLocal
from app.models import User, Document, Page, Paragraph, ClickedWord, HighlightedWord, VocabularyEntry, CalibrationItem, CalibrationResponse
from pydantic import BaseModel
import random
import re
import uuid
from pathlib import Path
from app.config import settings
from app.parsers.plain_text import parse_txt
from app.lib.translators.factory import get_translator
from app.lib.sentences import find_sentence
import csv
import io
import os
import pdfplumber
from datetime import date
from fastapi.responses import StreamingResponse

_WORD_RE = re.compile(r"[a-zA-Z]+(?:['\-][a-zA-Z]+)*")

# pdfplumber.extract_words() starts a new word when the gap between characters
# exceeds x_tolerance. Justified PDFs often have word gaps (~2.5pt) narrower than
# the 3pt default, so whole lines collapse into one token — which would produce
# line-spanning highlights. 2pt sits between the within-word (~0pt) and
# between-word gaps, splitting words correctly without breaking them apart.
_PDF_WORD_X_TOLERANCE = 2


def _extract_words(paragraphs: list[Paragraph]) -> list[str]:
    seen: set[str] = set()
    words: list[str] = []
    for para in paragraphs:
        for match in _WORD_RE.finditer(para.text):
            w = match.group()
            if w not in seen:
                seen.add(w)
                words.append(w)
    return words


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

def _prefetch_translation(paragraph_id: int, word: str, user_id: int, mode: str) -> None:
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

        word_lower = word.lower()
        highlighted = (
            db.query(HighlightedWord)
            .filter(
                HighlightedWord.user_id == user_id,
                HighlightedWord.document_id == document.id,
                HighlightedWord.page_number == page.page_number,
                HighlightedWord.word == word_lower,
            )
            .first()
        )

        if highlighted and highlighted.translation_target:
            return

        sentence = find_sentence(paragraph.text, word)

        if not highlighted:
            highlighted = HighlightedWord(
                user_id=user_id,
                document_id=document.id,
                page_number=page.page_number,
                word=word_lower,
                context=sentence,
                mode=mode,
            )
            db.add(highlighted)

        try:
            result = get_translator().translate(word, context=sentence)
            if result:
                highlighted.translation_target = result.target
        except Exception as e:
            print(f"Prefetch translation error for '{word}': {e}")

        db.commit()
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
) -> None:
    # PDF counterpart to _prefetch_translation: PDFs have no paragraph rows, so
    # the page text comes from the client (already extracted) rather than the DB.
    db = SessionLocal()
    try:
        document = db.get(Document, document_id)
        if not document or document.user_id != user_id:
            return

        word_lower = word.lower()
        highlighted = (
            db.query(HighlightedWord)
            .filter(
                HighlightedWord.user_id == user_id,
                HighlightedWord.document_id == document_id,
                HighlightedWord.page_number == page_number,
                HighlightedWord.word == word_lower,
            )
            .first()
        )

        if highlighted and highlighted.translation_target:
            return

        sentence = find_sentence(page_text, word)

        if not highlighted:
            highlighted = HighlightedWord(
                user_id=user_id,
                document_id=document_id,
                page_number=page_number,
                word=word_lower,
                context=sentence,
                mode=mode,
            )
            db.add(highlighted)

        try:
            result = get_translator().translate(word, context=sentence)
            if result:
                highlighted.translation_target = result.target
        except Exception as e:
            print(f"PDF prefetch translation error for '{word}': {e}")

        db.commit()
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


@app.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return current_user

class UserSettingsUpdate(BaseModel):
    use_ml_predictions: bool

@app.patch("/users/me")
def update_me(
    payload: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current_user.use_ml_predictions = payload.use_ml_predictions
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
    if ext not in ("txt", "pdf"):
        raise HTTPException(400, f"Unsupported format: .{ext} (only .txt and .pdf)")

    # Read file (PDFs are binary and run larger than plain text)
    raw = await file.read()
    max_mb = 25 if ext == "pdf" else 5
    if len(raw) > max_mb * 1024 * 1024:
        raise HTTPException(400, f"File too large (max {max_mb} MB)")

    # Parse/validate content before touching the disk so a bad file leaves nothing
    # behind. txt: split into pages/paragraphs. pdf: confirm it opens and has pages.
    pages_data: list[list[str]] | None = None
    if ext == "txt":
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(400, "File is not valid UTF-8 text")
        pages_data = parse_txt(text)
        if not pages_data:
            raise HTTPException(400, "File appears to be empty")
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
    # they need no structural rows.
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

    db.commit()
    db.refresh(document)

    return {
        "id": document.id,
        "title": document.title,
        "page_count": len(pages_data) if pages_data is not None else pdf_page_count,
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

    document.last_page_read = page_number

    ml_highlights: list[str] | None = None
    if current_user.use_ml_predictions:
        ml_set = difficult_words_ml(_extract_words(paragraphs), current_user, db) or set()
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
    }

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
        text = pdf.pages[page_number - 1].extract_text() or ""

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
        text = page.extract_text() or ""

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
    for item in payload.words:
        background_tasks.add_task(_prefetch_translation, item.paragraph_id, item.word, current_user.id, mode)
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
    for word in payload.words:
        background_tasks.add_task(
            _prefetch_translation_pdf,
            payload.document_id,
            payload.page_number,
            word,
            payload.page_text,
            current_user.id,
            mode,
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
        clicked_context = payload.page_text
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
            result = get_translator().translate(payload.word, context=sentence)
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

    # Add a vocabulary card (user-facing). skip if identical (word, translation) already exists
    existing = (
        db.query(VocabularyEntry)
        .filter(
            VocabularyEntry.user_id == current_user.id,
            VocabularyEntry.word == payload.word,
            VocabularyEntry.translation == translation_text,
        )
        .first()
    )
    if not existing:
        db.add(VocabularyEntry(
            user_id=current_user.id,
            word=payload.word,
            context=sentence,
            translation=translation_text,
        ))

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

class DifficultyRequest(BaseModel):
    words: list[str]
@app.post("/difficulty")
def get_difficulty(
    payload: DifficultyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    difficult = difficult_words(payload.words, current_user, db)
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