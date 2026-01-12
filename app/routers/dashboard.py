from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List
import shutil
import os
import json
import pandas as pd
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
        # Use default from models if settings not found (though crud.get_settings shouldn't return None if accessed via settings page logic, but for safety)
        # We should use the same default as models.py
        default_mapping = '{"source_cols": ["A", "B", "C", "D", "E"], "target_cols": ["A", "B", "C", "D", "E"]}'
        mapping_rules = settings.column_mapping if settings else default_mapping
        
        # Run Comparison
        summary, result_df, preview_list = comparison.compare_excel_files(source_path, target_path, mapping_rules)
        
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
        
        # Return Summary and Preview Data (limit 200 rows -> 100 discrepancies * 2 rows each)
        # preview_list is already filtered for mismatches in comparison.py
        preview_data = preview_list[:200]
        
        return {
            "summary": summary,
            "preview": preview_data,
            "result_file": result_filename
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
