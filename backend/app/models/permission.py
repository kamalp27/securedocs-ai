"""SQLAlchemy 2.x DocumentPermission model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.document import Document


class DocumentPermission(Base):
    """Document Access Control List (ACL) entry granting user or role access."""

    __tablename__ = "document_permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    role_target: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    permission_level: Mapped[str] = mapped_column(
        String(50),
        default="view",
        nullable=False,
    )
    granted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        "Document",
        back_populates="permissions",
    )
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="permissions",
        foreign_keys=[user_id],
    )

    def __repr__(self) -> str:
        return f"<DocumentPermission doc={self.document_id} user={self.user_id} level={self.permission_level}>"
