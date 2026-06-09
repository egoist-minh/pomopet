from sqlalchemy import Column, String, Integer, DateTime, Enum, Boolean
from datetime import datetime
import enum
from app.database.database import Base

class Priority(str, enum.Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    priority = Column(Enum(Priority), default=Priority.MEDIUM)
    deadline = Column(String)
    completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Subtask(Base):
    __tablename__ = "subtasks"

    id = Column(String, primary_key=True)
    task_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    completed = Column(Boolean, default=False)

class SessionState(str, enum.Enum):
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Session(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    task_id = Column(String)
    duration = Column(Integer)  # in seconds
    time_left = Column(Integer)
    state = Column(Enum(SessionState), default=SessionState.RUNNING)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    distraction_count = Column(Integer, default=0)

class Settings(Base):
    __tablename__ = "settings"

    id = Column(String, primary_key=True)
    pet_name = Column(String, default="Pomo")
    ai_service = Column(String, default="openai")
    session_duration = Column(Integer, default=25)
    short_break = Column(Integer, default=5)
    long_break = Column(Integer, default=15)
    sessions_until_long_break = Column(Integer, default=4)
