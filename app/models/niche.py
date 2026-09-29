import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime
from app.database import Base


def _now():
    return datetime.utcnow()


class TargetNiche(Base):
    __tablename__ = "target_niches"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, unique=True, nullable=False, index=True)
    category = Column(String, default="all")  # tech, business, creative, lifestyle, custom
    is_active = Column(Boolean, default=True)  # whether currently selected as target niche in Step 1
    count = Column(String, default="5.0k")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)
