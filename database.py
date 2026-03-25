import os
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, Integer, Boolean, JSON, DateTime, UniqueConstraint
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./test.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ThreatLog(Base):
    __tablename__ = "threat_logs"
    id = Column(String, primary_key=True, index=True)
    username = Column(String, index=True)
    raw_input = Column(String)
    decision = Column(String)
    score = Column(Integer)
    level_id = Column(Integer, default=1)
    is_compromised = Column(Boolean, default=False)   # ← جديد
    trace = Column(JSON)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class CompletedLevel(Base):
    """تتبع الليفلز اللي خلصها كل يوزر"""
    __tablename__ = "completed_levels"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, index=True)
    level_id = Column(Integer)
    completed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("username", "level_id", name="uq_user_level"),)

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()