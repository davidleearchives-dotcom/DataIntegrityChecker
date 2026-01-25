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

def process_comparison_task(task_id: str, source_path: str, target_path: str, mapping_rules: str, current_user_id: int, db: Session, source_include_dup: bool = False, target_include_dup: bool = False):
    try:
        tasks[task_id]["status"] = "processing"
        
        def progress_callback(percent, message):
            tasks[task_id]["progress"] = percent
            tasks[task_id]["message"] = message
            
        # Run Comparison with Duplicate Options
        summary, result_df, preview_list = comparison.compare_excel_files(
            source_path, target_path, mapping_rules, progress_callback,
            source_include_dup=source_include_dup, target_include_dup=target_include_dup
        )
        
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

@router.post("/analyze_file")
async def analyze_file(
    file: UploadFile = File(...),
    column_mapping: str = Form(None)  # Receive mapping rules
):
    """
    Analyzes the uploaded file to count total rows and unique rows based on key column.
    """
    try:
        # Save temporarily to read
        # Check extension
        filename = file.filename.lower()
        if filename.endswith(('.csv', '.txt')):
            df = pd.read_csv(file.file, dtype=str)
        else:
            df = pd.read_excel(file.file, dtype=str)
            
        # Data Normalization (Strip whitespace, Fill NaN)
        # This ensures the unique count matches the comparison logic
        df = df.fillna("")
        df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
            
        total_rows = len(df)
        unique_rows = total_rows
        
        # If column mapping is provided, calculate unique rows based on Key Columns
        if column_mapping:
            try:
                mapping = json.loads(column_mapping)
                cols = mapping.get("cols", [])
                
                if cols:
                    # Convert column letters to indices
                    def col2num(col_str):
                        expn = 0
                        col_num = 0
                        for char in reversed(col_str):
                            col_num += (ord(char.upper()) - ord('A') + 1) * (26 ** expn)
                            expn += 1
                        return col_num - 1

                    col_indices = [col2num(c.strip()) for c in cols]
                    
                    # Filter valid indices
                    valid_indices = [idx for idx in col_indices if idx < df.shape[1]]
                    
                    if valid_indices:
                        # Get Data from ALL mapped columns
                        subset_df = df.iloc[:, valid_indices]
                        
                        # Remove rows where ALL key columns are empty OR NaN
                        # This prevents counting trailing empty rows as "duplicates"
                        # dropna(how='all') might miss empty strings that are not NaN.
                        # So we first replace empty strings with NaN for this check.
                        subset_df_clean = subset_df.replace(r'^\s*$', float('nan'), regex=True).dropna(how='all')
                        
                        # Normalize Data: Simply concatenate string values (after stripping per cell)
                        # User Request: "=E2 & F2 & G2" logic
                        # This respects internal spaces but removes surrounding spaces
                        
                        def concat_keys(row):
                            # Convert to string, strip whitespace, then join
                            return "".join([str(val).strip() for val in row])

                        # Create a temporary normalized key series from the CLEANED dataframe
                        normalized_keys = subset_df_clean.apply(concat_keys, axis=1)
                        
                        # Count unique normalized keys
                        unique_rows = normalized_keys.nunique()
                        
                        duplicate_list = []
                        # Debugging: If difference is small, print duplicates
                        if len(subset_df_clean) - unique_rows > 0:
                            dups = normalized_keys[normalized_keys.duplicated(keep=False)]
                            # Get the original concatenated keys for display
                            # Limit to ALL duplicates (no limit)
                            duplicate_list = dups.tolist()
                            # Dedup the list itself for cleaner display
                            duplicate_list = list(set(duplicate_list))
                            print(f"Found {len(dups)} duplicate keys (sample): {duplicate_list[:5]}")
            except Exception as e:
                print(f"Error calculating unique rows: {e}")
                pass
            
        return {
            "total_rows": total_rows,
            "unique_rows": unique_rows,
            "duplicate_list": duplicate_list if 'duplicate_list' in locals() else []
        }
    except Exception as e:
        return JSONResponse(status_code=400, content={"detail": str(e)})

@router.post("/compare")
def compare_files(
    background_tasks: BackgroundTasks,
    source_file: UploadFile = File(...),
    target_file: UploadFile = File(...),
    source_include_dup: bool = Form(False),
    target_include_dup: bool = Form(False),
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
            None, # DB session not passed, created inside
            source_include_dup,
            target_include_dup
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
