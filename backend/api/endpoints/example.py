# backend/api/endpoints/example.py
from fastapi import APIRouter
from models.schemas import ExampleRequest, ExampleResponse
from services.example_service import run_example_logic

router = APIRouter(prefix="/example", tags=["Example"])

@router.post("/", response_model=ExampleResponse)
def run_example(request: ExampleRequest):
    result = run_example_logic(request)
    return ExampleResponse(result=result)
    