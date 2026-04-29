from datetime import datetime
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    reading_level: Mapped[str | None] = mapped_column(String(2), nullable=True) # we trust that only correct values will be passed like A1, etc.
    use_ml_predictions: Mapped[bool] = mapped_column(default=False, server_default="false")

