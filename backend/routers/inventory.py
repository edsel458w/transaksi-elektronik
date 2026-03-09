from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db, Produk

router = APIRouter(prefix="/inventory", tags=["Inventory"])

class ProdukCreate(BaseModel):
    nama_produk: str
    harga: int
    stok: int

@router.get("/")
def get_inventory(db: Session = Depends(get_db)):
    items = db.query(Produk).all()
    return {"status": "success", "data": items}

@router.get("/{item_id}")
def get_inventory_by_id(item_id: int):
    return {"status": "success", "message": "Inventory API berjalan!"}

@router.post('/')
def create_inventory(item: ProdukCreate, db: Session = Depends(get_db)):
    new_produk = Produk(
        nama_produk=item.nama_produk,
        harga=item.harga,
        stok=item.stok
    )

    db.add(new_produk)
    db.commit()
    db.refresh(new_produk)

    return {"status": "success", "data": new_produk }