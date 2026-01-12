from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from .. import database, schemas, models, auth, crud

router = APIRouter(tags=["Settings"])

@router.get("/settings", response_model=schemas.Settings)
async def read_settings(db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    settings = crud.get_settings(db, current_user.id)
    if not settings:
        settings = crud.create_settings(db, current_user.id)
    return settings

@router.put("/settings", response_model=schemas.Settings)
async def update_settings(settings: schemas.SettingsCreate, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    return crud.update_settings(db, current_user.id, settings)

@router.get("/users", response_model=List[schemas.User])
async def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_admin_user)):
    return crud.get_users(db, skip=skip, limit=limit)

@router.put("/users/{user_id}", response_model=schemas.User)
async def update_user_info(user_id: int, user_update: schemas.UserUpdate, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    # Users can update their own info, Admins can update anyone
    if current_user.role != "admin" and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    return crud.update_user(db, user_id, user_update)
