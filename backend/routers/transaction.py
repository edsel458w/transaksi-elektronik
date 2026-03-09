from fastapi import APIRouter

router = APIRouter()

@router.get("/transaction")
def get_transaction():
    return {"status": "success", "message": "Transaction API berjalan!"}