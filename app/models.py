from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    department = Column(String)
    contact = Column(String)
    role = Column(String, default="user")  # "admin" or "user"
    is_active = Column(Boolean, default=True)

    settings = relationship("Settings", back_populates="user", uselist=False)
    history = relationship("VerificationHistory", back_populates="user")

class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    # JSON string to store mapping rules. 
    # Example: {"source_columns": ["A", "B"], "target_columns": ["A", "B"]}
    column_mapping = Column(Text, default='{"source_cols": ["A", "B", "C", "D", "E"], "target_cols": ["A", "B", "C", "D", "E"]}') 
    
    user = relationship("User", back_populates="settings")

class VerificationHistory(Base):
    __tablename__ = "verification_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    timestamp = Column(DateTime, default=datetime.now)
    source_filename = Column(String)
    target_filename = Column(String)
    total_rows = Column(Integer)
    matched_count = Column(Integer)
    mismatched_count = Column(Integer)
    missing_source_count = Column(Integer)
    missing_target_count = Column(Integer)
    result_file_path = Column(String)

    user = relationship("User", back_populates="history")
