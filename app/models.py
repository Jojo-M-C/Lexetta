from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    reading_level: Mapped[str | None] = mapped_column(String(2), nullable=True) # we trust that only correct values will be passed like A1, etc.
    target_language: Mapped[str | None] = mapped_column(String(8), nullable=True)  # ISO code; null = not yet chosen. Set once at onboarding, then immutable.
    use_ml_predictions: Mapped[bool] = mapped_column(default=False, server_default="false")
    highlighting_enabled: Mapped[bool] = mapped_column(default=True, server_default="true")
    calibration_done: Mapped[bool] = mapped_column(default=False, server_default="false")

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    source_format: Mapped[str] = mapped_column(String(8))  # 'txt', 'epub', 'pdf'
    original_filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    # 0 means never opened: both readers set this to the page number as soon as
    # they fetch a page, so it only leaves 0 once the document is actually opened.
    # That keeps "never opened" (0%) distinct from "opened on page 1".
    last_page_read: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Total pages, recorded at upload. Stored rather than derived because PDFs have
    # no page rows to count, and the library needs it per document to show reading
    # progress. Nullable only for rows predating this column.
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Null for participant uploads; the CEFR level (A1–C2) for a text assigned at
    # onboarding. Marks study texts and records which level's text it is, so the
    # assignment stays idempotent and read_words can be joined back to the source.
    study_level: Mapped[str | None] = mapped_column(String(2), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())

class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chapter_index: Mapped[int] = mapped_column(Integer)  # reading order, 0-based
    title: Mapped[str] = mapped_column(String(512))

class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    # Set for EPUB pages (which belong to a chapter); null for txt/pdf.
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=True, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer)

class Paragraph(Base):
    __tablename__ = "paragraphs"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), index=True
    )
    paragraph_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class EpubImage(Base):
    __tablename__ = "epub_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(
        ForeignKey("pages.id", ondelete="CASCADE"), index=True
    )
    href: Mapped[str] = mapped_column(Text)              # zip-internal path of the image
    alt: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_paragraph_index: Mapped[int] = mapped_column(Integer)  # page-local; -1 = top of page


class ReadWord(Base):
    """Verified training data for the difficulty model.

    A row means "this word was on a page the user demonstrably read" (dwell time
    scaled by word count crossed a threshold), giving trustworthy labels: every
    read word is either a positive (was_clicked) or a negative (seen, not clicked).
    Two write paths share the (user, document, page, word) key: a click upserts
    was_clicked=True, and a page-read commit backfills the rest of the page's words
    without ever downgrading was_clicked.
    """
    __tablename__ = "read_words"
    __table_args__ = (
        UniqueConstraint("user_id", "document_id", "page_number", "word", name="uq_read_user_doc_page_word"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True  # keep the context for training even if the document is deleted
    )
    # Set for txt/epub (which have paragraph rows); NULL for pdf, which has none.
    paragraph_id: Mapped[int | None] = mapped_column(
        ForeignKey("paragraphs.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int] = mapped_column(Integer)

    word: Mapped[str] = mapped_column(String(128))           # surface form, lowercased (matches highlighted_words)
    context: Mapped[str] = mapped_column(Text)               # paragraph text (txt/epub) or sentence (pdf) it appeared in
    was_clicked: Mapped[bool] = mapped_column(default=False, server_default="false")
    was_highlighted: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Which prediction system was in effect for this row: "ml" or "cefr". For a
    # highlighted word it's the model that flagged it; for a read-but-not-highlighted
    # word it's the model that was active and did not flag it (the ML/CEFR negative).
    # Nullable only for rows written before this column existed.
    mode: Mapped[str | None] = mapped_column(String(8), nullable=True)
    highlighted_word_id: Mapped[int | None] = mapped_column(
        ForeignKey("highlighted_words.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

class WordCefrLevel(Base):
    __tablename__ = "word_cefr_levels"

    word: Mapped[str] = mapped_column(String(128), primary_key=True)
    cefr_level: Mapped[str] = mapped_column(String(2))

class HighlightedWord(Base):
    __tablename__ = "highlighted_words"
    __table_args__ = (
        UniqueConstraint("user_id", "document_id", "page_number", "word", name="uq_highlighted_user_doc_page_word"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    page_number: Mapped[int] = mapped_column(Integer)
    word: Mapped[str] = mapped_column(String(128))
    context: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(8))  # "ml" or "cefr"
    was_clicked: Mapped[bool] = mapped_column(default=False, server_default="false")
    translation_target: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class VocabularyEntry(Base):
    __tablename__ = "vocabulary_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    word: Mapped[str] = mapped_column(String(128))
    context: Mapped[str] = mapped_column(Text)
    translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CalibrationItem(Base):
    __tablename__ = "calibration_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    word: Mapped[str] = mapped_column(String(128))
    sentence: Mapped[str] = mapped_column(Text)
    cefr_level: Mapped[str] = mapped_column(String(2))


class CalibrationResponse(Base):
    __tablename__ = "calibration_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("calibration_items.id", ondelete="CASCADE"), index=True
    )
    difficulty_rating: Mapped[int] = mapped_column(Integer)  # 1–5
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

