from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import shutil
import os
import json
import pandas as pd
import uuid
import time
from datetime import datetime
from .. import database, schemas, models, auth, crud
from ..services import comparison, excel_handler

router = APIRouter(tags=["Dashboard"])

UPLOAD_DIR = "uploads"
RESULTS_DIR = "results"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# In-memory storage for tasks
# task_id -> {"status": "processing", "progress": 0, "message": "Starting...", "result": None, "error": None, "start_time": timestamp}
tasks: Dict[str, Dict[str, Any]] = {}

def process_comparison_task(task_id: str, source_path: str, target_path: str, mapping_rules: str, current_user_id: int, db: Session):
    try:
        tasks[task_id]["status"] = "processing"
        
        def progress_callback(percent, message):
            tasks[task_id]["progress"] = percent
            tasks[task_id]["message"] = message
            
        # Run Comparison
        summary, result_df, preview_list = comparison.compare_excel_files(source_path, target_path, mapping_rules, progress_callback)
        
        # Update progress before saving
        tasks[task_id]["progress"] = 95
        tasks[task_id]["message"] = "Saving result file..."
        
        # Generate Result Excel
        result_filename = f"Result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        result_path = os.path.join(RESULTS_DIR, result_filename)
        excel_handler.generate_styled_excel(result_df, result_path)
        
        # Save History
        history_data = schemas.HistoryCreate(
            source_filename=tasks[task_id]["source_filename"],
            target_filename=tasks[task_id]["target_filename"],
            total_rows=summary["total_rows"],
            matched_count=summary["matched"],
            mismatched_count=summary["mismatched"],
            missing_source_count=summary["missing_source"],
            missing_target_count=summary["missing_target"],
            result_file_path=result_path
        )
        # Note: We need a fresh DB session here if this runs in background? 
        # Actually, BackgroundTasks runs in the same loop but usually we should be careful with DB sessions.
        # FastAPI's Depends(get_db) session closes after request.
        # So we should create a new session or pass one that is managed manually.
        # However, FastAPI BackgroundTasks can accept the session if we don't close it?
        # Better: Create a new session for the background task.
        
        new_db = database.SessionLocal()
        try:
            crud.create_history(new_db, history_data, current_user_id)
        finally:
            new_db.close()
        
        preview_data = preview_list[:200]
        
        tasks[task_id]["result"] = {
            "summary": summary,
            "preview": preview_data,
            "result_file": result_filename
        }
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["message"] = "Comparison completed!"
        
    except Exception as e:
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["message"] = f"Error: {str(e)}"

@router.post("/compare")
def compare_files(
    background_tasks: BackgroundTasks,
    source_file: UploadFile = File(...),
    target_file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(database.get_db)
):
    try:
        task_id = str(uuid.uuid4())
        
        # Save uploaded files
        source_path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{source_file.filename}")
        target_path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{target_file.filename}")
        
        with open(source_path, "wb") as buffer:
            shutil.copyfileobj(source_file.file, buffer)
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(target_file.file, buffer)
            
        # Get User Settings for Mapping
        settings = crud.get_settings(db, current_user.id)
        default_mapping = '{"source_cols": ["A", "B", "C", "D", "E"], "target_cols": ["A", "B", "C", "D", "E"]}'
        mapping_rules = settings.column_mapping if settings else default_mapping
        
        # Initialize Task
        tasks[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "Queued...",
            "source_filename": source_file.filename,
            "target_filename": target_file.filename,
            "start_time": time.time()
        }
        
        # Start Background Task
        # We pass necessary data. DB session is handled inside.
        background_tasks.add_task(
            process_comparison_task, 
            task_id, 
            source_path, 
            target_path, 
            mapping_rules, 
            current_user.id,
            None # DB session not passed, created inside
        )
        
        return {"task_id": task_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    elapsed = time.time() - task["start_time"]
    
    return {
        "status": task["status"],
        "progress": task["progress"],
        "message": task["message"],
        "elapsed": elapsed,
        "result": task.get("result"), # Only present if completed
        "error": task.get("error")
    }

@router.get("/download/{filename}")
async def download_result(
    filename: str, 
    token: str = None, # Allow token in query param
    db: Session = Depends(database.get_db)
):
    # Manually validate token if provided in query param (for browser downloads)
    if token:
        try:
            # Re-use logic from auth.get_current_user but adapted
            # Or simply call auth.get_current_user with the token string?
            # auth.get_current_user expects "Depends(oauth2_scheme)" which extracts from Header.
            # We need a manual check here.
            from jose import jwt, JWTError
            from .. import schemas
            
            payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                raise HTTPException(status_code=401, detail="Invalid token")
            # We don't necessarily need full user object for download, just valid auth.
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        # If no token param, try standard Dependency (works for API calls, fails for browser direct link without header)
        # But browser link won't send header. So we MUST rely on token param for this route.
        # Unless we make it public? No, security first.
        raise HTTPException(status_code=401, detail="Not authenticated")

    file_path = os.path.join(RESULTS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename)
