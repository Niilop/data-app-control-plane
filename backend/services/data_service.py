# backend/services/data_service.py
import pandas as pd
import os
from sqlalchemy.orm import Session
from models.database import DataCatalog
from models.schemas import DataCatalogCreate
import json
from typing import List


def process_and_save_dataset(db: Session, user_id: int, file_path: str, name: str, description: str):
    
    # 1. Profile the data
    df = pd.read_csv(file_path) # Assume CSV for now
    
    
    metadata = {
        "num_rows": int(df.shape[0]),
        "num_cols": int(df.shape[1]),
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "missing_values": df.isnull().sum().to_dict(),
        "summary_stats": df.describe(include='all').to_json()
    }

    # 2. Save to Database
    db_catalog = DataCatalog(
        user_id=user_id,
        name=name,
        file_path=file_path,
        description=description,
        data_metadata=metadata
    )
    
    db.add(db_catalog)
    db.commit()
    db.refresh(db_catalog)
    return db_catalog

def get_user_datasets(db: Session, user_id: int) -> List[DataCatalog]:
    """Retrieve all datasets uploaded by a specific user."""
    return db.query(DataCatalog).filter(DataCatalog.user_id == user_id).all()

def count_user_datasets(db: Session, user_id: int) -> int:
    """Count the total number of datasets uploaded by a specific user."""
    return db.query(DataCatalog).filter(DataCatalog.user_id == user_id).count()