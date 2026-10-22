"""Append-only Channelmanager snapshots; never references or mutates live products."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, JSON, DateTime, ForeignKey, UniqueConstraint
from database import Base


class ChannelSnapshot(Base):
    __tablename__ = "channel_snapshot"
    __table_args__ = (UniqueConstraint("shop_id", "kind", "revision"),
                      UniqueConstraint("shop_id", "claim"),)
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(24), nullable=False)
    revision = Column(Integer, nullable=False)
    claim = Column(String(100), nullable=True)
    status = Column(String(24), nullable=False, default="draft")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String(255), nullable=False)
    data = Column(JSON, nullable=False)
