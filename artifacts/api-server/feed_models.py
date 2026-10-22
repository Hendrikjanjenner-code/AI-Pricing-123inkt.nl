"""Separate, inactive-by-default Hub integrations. File bytes live only in App Storage."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, DateTime, ForeignKey, UniqueConstraint
from database import Base


class HubFeedProfile(Base):
    __tablename__ = "hub_feed_profile"
    id = Column(Integer, primary_key=True)
    shop_id = Column(Integer, ForeignKey("dim_shop.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    purpose = Column(String(24), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    active = Column(Boolean, nullable=False, default=False)
    config = Column(JSON, nullable=False, default=dict)
    credentials = Column(Text)
    token_hash = Column(String(64))
    token_rotated_at = Column(DateTime)
    last_feed_access = Column(DateTime)
    validated_version_id = Column(Integer)
    current_version_id = Column(Integer)
    released_version_id = Column(Integer)
    last_attempt = Column(DateTime)
    last_success = Column(DateTime)
    last_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String(255), nullable=False)


class HubFeedVersion(Base):
    __tablename__ = "hub_feed_version"
    __table_args__ = (UniqueConstraint("profile_id", "config_revision", "sha256", "context_hash"),)
    id = Column(Integer, primary_key=True)
    profile_id = Column(Integer, ForeignKey("hub_feed_profile.id"), nullable=False, index=True)
    config_revision = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    context_hash = Column(String(64), nullable=False, default="")
    object_key = Column(Text, nullable=False)
    records_key = Column(Text, nullable=False)
    status = Column(String(24), nullable=False)
    row_count = Column(Integer, nullable=False)
    report = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String(255), nullable=False)
