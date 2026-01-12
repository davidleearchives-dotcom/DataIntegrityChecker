from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class UserBase(BaseModel):
    username: str
    full_name: Optional[str] = None
    department: Optional[str] = None
    contact: Optional[str] = None
    role: str = "user"

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    password: Optional[str] = None
    full_name: Optional[str] = None
    department: Optional[str] = None
    contact: Optional[str] = None

class User(UserBase):
    id: int
    is_active: bool
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class SettingsBase(BaseModel):
    column_mapping: str

class SettingsCreate(SettingsBase):
    pass

class Settings(SettingsBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True

class HistoryBase(BaseModel):
    source_filename: str
    target_filename: str
    total_rows: int
    matched_count: int
    mismatched_count: int
    missing_source_count: int
    missing_target_count: int
    result_file_path: str

class HistoryCreate(HistoryBase):
    pass

class History(HistoryBase):
    id: int
    user_id: int
    timestamp: datetime

    class Config:
        from_attributes = True
