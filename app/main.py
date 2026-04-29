from fastapi import Depends, FastAPI, Header, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Document, Page, Paragraph, LookupEvent
from pydantic import BaseModel

import os
import uuid
from pathlib import Path

from app.config import settings
from app.parsers.plain_text import parse_txt
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
    if ext != "txt":
        raise HTTPException(400, f"Unsupported format: .{ext} (only .txt for now)")

    # Read file
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:  # 5 MB cap for txt
        raise HTTPException(400, "File too large (max 5 MB)")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "File is not valid UTF-8 text")

    # Parse
    pages_data = parse_txt(text)
    if not pages_data:
        raise HTTPException(400, "File appears to be empty")

    # Save original to disk
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid.uuid4()}.{ext}"
    file_path = upload_dir / stored_filename
    file_path.write_bytes(raw)

    # Title = filename without extension
    title = file.filename.rsplit(".", 1)[0]

    # Create database rows
    document = Document(
        user_id=current_user.id,
        title=title,
        source_format=ext,
        original_filename=file.filename,
        file_path=str(file_path),
    )
    db.add(document)
    db.flush()  # assigns document.id without committing

    for page_idx, paragraphs in enumerate(pages_data, start=1):
        page = Page(document_id=document.id, page_number=page_idx)
        db.add(page)
        db.flush()

        for para_idx, text in enumerate(paragraphs):
            db.add(Paragraph(
                page_id=page.id,
                paragraph_index=para_idx,
                text=text,
            ))

    db.commit()
    db.refresh(document)

    return {
        "id": document.id,
        "title": document.title,
        "page_count": len(pages_data),
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
    db.commit()

    return {
        "document_id": document_id,
        "title": document.title,
        "page_number": page_number,
        "total_pages": total_pages,
        "paragraphs": [{"id": p.id, "text": p.text} for p in paragraphs],
    }

class LookupCreate(BaseModel):
    paragraph_id: int
    word: str
    was_highlighted: bool
    mode: str = "translate"

@app.post("/lookups")
def create_lookup(
    payload: LookupCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    paragraph = db.get(Paragraph, payload.paragraph_id)
    if not paragraph:
        raise HTTPException(404, "Paragraph not found")

    # Verify the paragraph belongs to a document this user owns
    page = db.get(Page, paragraph.page_id)
    if not page:
        raise HTTPException(404, "Page not found")
    document = db.get(Document, page.document_id)
    if not document or document.user_id != current_user.id:
        raise HTTPException(404, "Document not found")

    event = LookupEvent(
        user_id=current_user.id,
        document_id=document.id,
        paragraph_id=paragraph.id,
        word=payload.word,
        context=paragraph.text,
        was_highlighted=payload.was_highlighted,
        mode=payload.mode,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return {
        "id": event.id,
        "occurred_at": event.occurred_at,
    }