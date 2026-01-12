from sqlalchemy.orm import Session
from . import models, schemas, auth

def get_user(db: Session, user_id: int):
    return db.query(models.User).filter(models.User.id == user_id).first()

def get_user_by_username(db: Session, username: str):
    return db.query(models.User).filter(models.User.username == username).first()

def get_users(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.User).offset(skip).limit(limit).all()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        hashed_password=hashed_password,
        full_name=user.full_name,
        department=user.department,
        contact=user.contact,
        role=user.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    # Create default settings for new user
    create_settings(db, db_user.id)
    return db_user

def update_user(db: Session, user_id: int, user_update: schemas.UserUpdate):
    db_user = get_user(db, user_id)
    if not db_user:
        return None
    if user_update.password:
        db_user.hashed_password = auth.get_password_hash(user_update.password)
    if user_update.full_name:
        db_user.full_name = user_update.full_name
    if user_update.department:
        db_user.department = user_update.department
    if user_update.contact:
        db_user.contact = user_update.contact
    if user_update.role:
        db_user.role = user_update.role
    db.commit()
    db.refresh(db_user)
    return db_user

def delete_user(db: Session, user_id: int):
    db_user = get_user(db, user_id)
    if db_user:
        db.delete(db_user)
        db.commit()
    return db_user

def create_settings(db: Session, user_id: int):
    db_settings = models.Settings(user_id=user_id)
    db.add(db_settings)
    db.commit()
    db.refresh(db_settings)
    return db_settings

def get_settings(db: Session, user_id: int):
    return db.query(models.Settings).filter(models.Settings.user_id == user_id).first()

def update_settings(db: Session, user_id: int, settings: schemas.SettingsBase):
    db_settings = get_settings(db, user_id)
    if not db_settings:
        db_settings = create_settings(db, user_id)
    db_settings.column_mapping = settings.column_mapping
    db.commit()
    db.refresh(db_settings)
    return db_settings

def create_history(db: Session, history: schemas.HistoryCreate, user_id: int):
    db_history = models.VerificationHistory(**history.dict(), user_id=user_id)
    db.add(db_history)
    db.commit()
    db.refresh(db_history)
    return db_history

def get_history(db: Session, user_id: int, skip: int = 0, limit: int = 100):
    return db.query(models.VerificationHistory).filter(models.VerificationHistory.user_id == user_id).order_by(models.VerificationHistory.timestamp.desc()).offset(skip).limit(limit).all()
