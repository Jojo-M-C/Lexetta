from datetime import datetime
from sqlalchemy import String, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.database import Base
from sqlalchemy.dialects.postgresql import JSONB

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    reading_level: Mapped[str | None] = mapped_column(String(2), nullable=True) # we trust that only correct values will be passed like A1, etc.
    use_ml_predictions: Mapped[bool] = mapped_column(default=False, server_default="false")

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    source_format: Mapped[str] = mapped_column(String(8))  # 'txt', 'md', 'pdf'
    original_filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(Text)
    last_page_read: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    uploaded_at: Mapped[datetime] = mapped_column(server_default=func.now())

class Page(Base):
    __tablename__ = "pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
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


class LookupEvent(Base):
    __tablename__ = "lookup_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    paragraph_id: Mapped[int] = mapped_column(
        ForeignKey("paragraphs.id", ondelete="SET NULL"), nullable=True
    )

    word: Mapped[str] = mapped_column(String(128))           # the surface form clicked
    context: Mapped[str] = mapped_column(Text)               # the sentence/paragraph it was in (snapshot)
    was_highlighted: Mapped[bool] = mapped_column()          # was the system already showing this as difficult?
    mode: Mapped[str] = mapped_column(String(16))            # 'translate' or 'explain'

    occurred_at: Mapped[datetime] = mapped_column(server_default=func.now())

class WordCefrLevel(Base):
    __tablename__ = "word_cefr_levels"

    word: Mapped[str] = mapped_column(String(128), primary_key=True)
    cefr_level: Mapped[str] = mapped_column(String(2))

class TranslationCache(Base):
    __tablename__ = "translation_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_text: Mapped[str] = mapped_column(String(256))
    context_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_lang: Mapped[str] = mapped_column(String(8))
    target_lang: Mapped[str] = mapped_column(String(8))
    provider: Mapped[str] = mapped_column(String(32))
    translations: Mapped[list] = mapped_column(JSONB)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_used_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "source_text", "context_hash", "source_lang", "target_lang", "provider",
            name="uq_translation_cache_lookup"
        ),
    )
