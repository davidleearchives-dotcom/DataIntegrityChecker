from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List
import shutil
import os
import json
from datetime import datetime
from .. import database, schemas, models, auth, crud
from ..services import comparison, excel_handler

router = APIRouter(tags=["Dashboard"])

UPLOAD_DIR = "uploads"
RESULTS_DIR = "results"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

@router.post("/compare")
async def compare_files(
    source_file: UploadFile = File(...),
    target_file: UploadFile = File(...),
    current_user: models.User = Depends(auth.get_current_active_user),
    db: Session = Depends(database.get_db)
):
    try:
        # Save uploaded files
        source_path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{source_file.filename}")
        target_path = os.path.join(UPLOAD_DIR, f"{datetime.now().timestamp()}_{target_file.filename}")
        
        with open(source_path, "wb") as buffer:
            shutil.copyfileobj(source_file.file, buffer)
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(target_file.file, buffer)
            
        # Get User Settings for Mapping
        settings = crud.get_settings(db, current_user.id)
        mapping_rules = settings.column_mapping if settings else '{"source_cols": ["A", "B"], "target_cols": ["A", "B"]}'
        
        # Run Comparison
        summary, result_df = comparison.compare_excel_files(source_path, target_path, mapping_rules)
        
        # Generate Result Excel
        result_filename = f"Result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        result_path = os.path.join(RESULTS_DIR, result_filename)
        excel_handler.generate_styled_excel(result_df, result_path)
        
        # Save History
        history_data = schemas.HistoryCreate(
            source_filename=source_file.filename,
            target_filename=target_file.filename,
            total_rows=summary["total_rows"],
            matched_count=summary["matched"],
            mismatched_count=summary["mismatched"],
            missing_source_count=summary["missing_source"],
            missing_target_count=summary["missing_target"],
            result_file_path=result_path
        )
        crud.create_history(db, history_data, current_user.id)
        
        # Return Summary and Preview Data (limit 100 rows for preview)
        # Filter for non-matches first
        mismatches_df = result_df[result_df['Verification_Result'] != 'Match']
        if len(mismatches_df) > 0:
            preview_df = mismatches_df.head(100)
        else:
            preview_df = result_df.head(100)
            
        preview_data = preview_df.fillna("").to_dict(orient="records")
        
        return {
            "summary": summary,
            "preview": preview_data,
            "result_file": result_filename
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download/{filename}")
async def download_result(filename: str, current_user: models.User = Depends(auth.get_current_active_user)):
    file_path = os.path.join(RESULTS_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename)
