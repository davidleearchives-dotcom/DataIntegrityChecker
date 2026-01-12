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
    # Check if target user exists
    target_user = crud.get_user(db, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Permission Logic
    is_self = current_user.id == user_id
    is_admin = current_user.role == "admin"
    
    # 1. Normal user cannot edit others
    if not is_self and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # 2. Admin cannot edit other admins
    if is_admin and not is_self:
        if target_user.role == "admin":
            raise HTTPException(status_code=403, detail="Cannot edit other admin accounts")

    # 3. Role Update Logic
    if user_update.role:
        # Only Admin can change roles
        if not is_admin:
             raise HTTPException(status_code=403, detail="Only admins can change roles")
        # Cannot change own role (prevent self-lockout)
        if is_self:
             raise HTTPException(status_code=400, detail="Cannot change your own role")
             
    return crud.update_user(db, user_id, user_update)
