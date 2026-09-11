# backend/api/endpoints/data.py
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from sqlalchemy.orm import Session
from models.schemas import DataCatalogResponse
from core.config import Settings, get_settings
from core.database import get_db
from models.database import User
from services.data_service import process_and_save_dataset, get_user_datasets, count_user_datasets
from api.endpoints.auth import get_current_user
from werkzeug.utils import secure_filename
from pathlib import Path
from typing import List
import shutil

router = APIRouter(prefix="/data", tags=["Data Catalog"])

# Define the maximum file size (10 MB in bytes)
MAX_FILE_SIZE = 10 * 1024 * 1024

@router.post("/upload")
async def upload_data(
    name: str = Form(...),
    description: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # <** MAGIC HAPPENS HERE
    settings: Settings = Depends(get_settings),
):
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    # 1. Limit Check: Enforce maximum of 10 datasets
    current_count = count_user_datasets(db, current_user.id)
    if current_count >= 10:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Storage limit reached. You can only upload a maximum of 10 datasets."
        )

    # 2. Limit Check: Enforce file size limit (10MB)
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size exceeds the 10MB limit. Your file is {file.size / (1024 * 1024):.2f}MB."
        )
    
    # 3. Save physical file
    safe_filename = secure_filename(file.filename)
    raw_dir = Path(settings.data_dir) / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_location = raw_dir / safe_filename

    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 4. Process and Catalog
    try:
        catalog_entry = process_and_save_dataset(
            db, current_user.id, str(file_location), name, description
        )
        return catalog_entry
    except Exception as e:
        # Cleanup file if processing fails
        if file_location.exists():
            file_location.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to process data: {str(e)}")
    

@router.get("/", response_model=List[DataCatalogResponse])
def list_datasets(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all datasets for the authenticated user."""
    # Look how clean this is now!
    return get_user_datasets(db, current_user.id)


@router.get("/count")
def get_dataset_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get the total number of datasets uploaded by the authenticated user."""
    count = count_user_datasets(db, current_user.id)
    
    return {
        "count": count,
        "limit": 10,
        "remaining": 10 - count
    }