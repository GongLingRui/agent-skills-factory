"""ORM: file_uploads."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from agent_factory.db.base import Base


class FileUpload(Base):
    """Uploaded file metadata (content stays in object storage)."""

    __tablename__ = "file_uploads"

    file_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64))
    user_id_hash: Mapped[str] = mapped_column(String(64))
    file_name: Mapped[str] = mapped_column(String(256))
    file_size: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64))
    storage_path: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    extracted_text_path: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
