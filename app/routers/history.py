from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from .. import database, schemas, models, auth, crud

router = APIRouter(tags=["History"])

@router.get("/history", response_model=List[schemas.History])
async def read_history(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db), current_user: models.User = Depends(auth.get_current_active_user)):
    return crud.get_history(db, user_id=current_user.id, skip=skip, limit=limit)
