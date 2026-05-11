"""
routers/midtrans_payment.py
Payment Gateway Midtrans — SecureTransact

Endpoint untuk integrasi pembayaran melalui Midtrans Snap:
  - POST /payment/create-snap-token  → Buat Snap Token untuk payment popup
  - POST /payment/notification       → Webhook notification dari Midtrans
  - GET  /payment/status/{order_id}  → Cek status pembayaran
  - GET  /payment/history            → Riwayat pembayaran
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import hashlib
import json
import logging
import os

from database import get_db
from models import Transaksi, User, PaymentLog
from core.deps import get_current_user

router = APIRouter(prefix="/payment", tags=["Payment Gateway"])
logger = logging.getLogger(__name__)

from dotenv import load_dotenv

# ── Midtrans Config ──────────────────────────────────────────
# Load .env dari root backend
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(backend_dir, '.env'))

MIDTRANS_SERVER_KEY = os.getenv("MIDTRANS_SERVER_KEY")
MIDTRANS_CLIENT_KEY = os.getenv("MIDTRANS_CLIENT_KEY")
# Pastikan perbandingan boolean benar
MIDTRANS_IS_PRODUCTION = str(os.getenv("MIDTRANS_IS_PRODUCTION", "False")).lower() == "true"

MIDTRANS_SNAP_URL = "https://app.midtrans.com/snap/v1/transactions" if MIDTRANS_IS_PRODUCTION else "https://app.sandbox.midtrans.com/snap/v1/transactions"

MIDTRANS_STATUS_URL = (
    "https://api.midtrans.com/v2"
    if MIDTRANS_IS_PRODUCTION
    else "https://api.sandbox.midtrans.com/v2"
)


# ══════════════════════════════════════════════════════════════
#  Schemas
# ══════════════════════════════════════════════════════════════

class PaymentCreateRequest(BaseModel):
    transaksi_id: int
    payment_type: str = "snap"  # snap | direct

class PaymentCreateResponse(BaseModel):
    snap_token: str
    redirect_url: str
    order_id: str
    gross_amount: int
    client_key: str

class PaymentRecord(BaseModel):
    id: int
    order_id: str
    transaksi_id: int
    transaksi_kode: str
    nama_klien: str
    gross_amount: int
    payment_type: str
    payment_status: str
    snap_token: Optional[str] = None
    is_demo: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    midtrans_response: Optional[str] = None

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  Helper: Generate Snap Token (Simulasi + Real)
# ══════════════════════════════════════════════════════════════

def _generate_order_id(transaksi_kode: str) -> str:
    """Generate unique order ID for Midtrans."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"ST-{transaksi_kode}-{timestamp}"


async def _create_snap_token_real(order_id: str, gross_amount: int, customer_name: str, items: list) -> dict:
    """
    Buat Snap Token via Midtrans API.
    Requires: pip install httpx
    """
    try:
        import httpx
        import base64
        
        auth_string = base64.b64encode(f"{MIDTRANS_SERVER_KEY}:".encode()).decode()
        
        payload = {
            "transaction_details": {
                "order_id": order_id,
                "gross_amount": gross_amount
            },
            "customer_details": {
                "first_name": customer_name,
            },
            "item_details": items,
            "enabled_payments": [
                "credit_card", "bca_va", "bni_va", "bri_va", "permata_va",
                "echannel", "gopay", "shopeepay", "qris", "dana",
                "indomaret", "alfamart"
            ],
            "credit_card": {
                "secure": True
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                MIDTRANS_SNAP_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Basic {auth_string}"
                },
                timeout=30.0
            )
            
            if response.status_code == 201:
                data = response.json()
                return {
                    "success": True,
                    "snap_token": data.get("token", ""),
                    "redirect_url": data.get("redirect_url", "")
                }
            else:
                error_msg = f"Midtrans API error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
                
    except ImportError:
        return {"success": False, "error": "httpx not installed"}
    except Exception as e:
        logger.error(f"Midtrans request failed: {e}")
        return {"success": False, "error": str(e)}


def _create_snap_token_demo(order_id: str, gross_amount: int) -> dict:
    """Simulasi Snap Token untuk mode demo (tanpa koneksi ke Midtrans)."""
    # Generate a demo token
    token_raw = f"{order_id}-{gross_amount}-{datetime.utcnow().isoformat()}"
    demo_token = hashlib.md5(token_raw.encode()).hexdigest()
    
    return {
        "success": True,
        "snap_token": f"demo-{demo_token[:24]}",
        "redirect_url": f"https://app.sandbox.midtrans.com/snap/v3/redirection/{demo_token[:24]}"
    }


# ══════════════════════════════════════════════════════════════
#  POST /payment/create-snap-token
# ══════════════════════════════════════════════════════════════

@router.post("/create-snap-token")
async def create_snap_token(
    payload: PaymentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Buat Snap Token Midtrans untuk membuka payment popup."""
    # Get transaction
    transaksi = db.query(Transaksi).filter(Transaksi.id == payload.transaksi_id).first()
    if not transaksi:
        raise HTTPException(status_code=404, detail="Transaksi tidak ditemukan.")
    
    # Generate order ID
    order_id = _generate_order_id(transaksi.kode)
    gross_amount = transaksi.grand_total
    
    # Build item details
    items = []
    for item in transaksi.items:
        items.append({
            "id": str(item.produk_id),
            "name": item.nama_produk[:50],  # Midtrans max 50 chars
            "price": item.harga,
            "quantity": item.qty
        })
    # Add discount as negative item so sum matches gross_amount
    if transaksi.diskon_nominal > 0:
        diskon_label = f"Diskon {transaksi.diskon_persen}%" if transaksi.diskon_persen > 0 else "Diskon"
        items.append({
            "id": "DISKON",
            "name": diskon_label,
            "price": -transaksi.diskon_nominal,
            "quantity": 1
        })
    # Add PPN as separate item
    if transaksi.ppn > 0:
        items.append({
            "id": "PPN",
            "name": "PPN 11%",
            "price": transaksi.ppn,
            "quantity": 1
        })
    
    # Try real Midtrans first
    # Fallback to demo ONLY if keys are missing
    is_demo = False
    if not MIDTRANS_SERVER_KEY:
        result = _create_snap_token_demo(order_id, gross_amount)
        is_demo = True
    else:
        result = await _create_snap_token_real(order_id, gross_amount, transaksi.nama_klien, items)
        if not result["success"]:
            # Jika ada error dari Midtrans (misal key salah), jangan fallback ke demo
            # tapi tampilkan error aslinya agar user tahu apa yang salah.
            raise HTTPException(status_code=400, detail=result.get("error", "Gagal memanggil Midtrans API"))
    
    # Save payment log to DB
    payment_log = PaymentLog(
        order_id=order_id,
        transaksi_id=transaksi.id,
        transaksi_kode=transaksi.kode,
        nama_klien=transaksi.nama_klien,
        gross_amount=gross_amount,
        payment_type="snap",
        payment_status="pending",
        snap_token=result["snap_token"],
        is_demo=is_demo,
        midtrans_response=json.dumps(result)
    )
    db.add(payment_log)
    
    # Update transaksi status to 'pending' if it was 'lunas' (because it's now waiting for payment)
    # Actually, transaction should be 'menunggu' initially.
    if transaksi.status == "lunas" and not is_demo:
        transaksi.status = "menunggu"
    
    db.commit()
    db.refresh(payment_log)
    
    return {
        "status": "success",
        "data": {
            "snap_token": result["snap_token"],
            "redirect_url": result.get("redirect_url", ""),
            "order_id": order_id,
            "gross_amount": gross_amount,
            "client_key": MIDTRANS_CLIENT_KEY,
            "is_demo": is_demo,
            "is_production": MIDTRANS_IS_PRODUCTION
        }
    }


# ══════════════════════════════════════════════════════════════
#  POST /payment/notification — Webhook dari Midtrans
# ══════════════════════════════════════════════════════════════

@router.post("/notification")
async def payment_notification(request: Request, db: Session = Depends(get_db)):
    """
    Webhook endpoint yang dipanggil oleh Midtrans setelah pembayaran.
    Midtrans mengirim notifikasi setiap ada perubahan status pembayaran.
    """
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    order_id = body.get("order_id", "")
    transaction_status = body.get("transaction_status", "")
    fraud_status = body.get("fraud_status", "")
    payment_type = body.get("payment_type", "")
    
    logger.info(f"[Midtrans] Notification: order={order_id}, status={transaction_status}, fraud={fraud_status}")
    
    # Verify signature — wajib ada dan valid sebelum memproses apapun
    signature_key = body.get("signature_key", "")
    status_code = body.get("status_code", "")
    gross_amount = body.get("gross_amount", "")
    expected_sig = hashlib.sha512(
        f"{order_id}{status_code}{gross_amount}{MIDTRANS_SERVER_KEY}".encode()
    ).hexdigest()

    if not signature_key or signature_key != expected_sig:
        logger.warning(f"[Midtrans] Invalid/missing signature for order {order_id}")
        raise HTTPException(status_code=403, detail="Invalid signature")
    
    # Determine payment status
    if transaction_status in ["capture", "settlement"]:
        if fraud_status == "accept" or not fraud_status:
            final_status = "settlement"
        else:
            final_status = "deny"
    elif transaction_status == "pending":
        final_status = "pending"
    elif transaction_status in ["deny", "cancel", "expire"]:
        final_status = transaction_status
    else:
        final_status = transaction_status
    
    # Update payment record in DB
    payment_log = db.query(PaymentLog).filter(PaymentLog.order_id == order_id).first()
    if payment_log:
        payment_log.payment_status = final_status
        payment_log.payment_type = payment_type
        payment_log.midtrans_response = json.dumps(body)
    
        # Update transaction status in DB
        if final_status == "settlement":
            trx = db.query(Transaksi).filter(Transaksi.id == payment_log.transaksi_id).first()
            if trx:
                trx.status = "lunas"
                trx.metode_pembayaran = payment_type or "midtrans"
        
        db.commit()
    
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════
#  GET /payment/status/{order_id} — Cek status pembayaran
# ══════════════════════════════════════════════════════════════

@router.get("/status/{order_id}")
async def get_payment_status(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cek status pembayaran berdasarkan order_id."""
    payment_log = db.query(PaymentLog).filter(PaymentLog.order_id == order_id).first()
    if not payment_log:
        raise HTTPException(status_code=404, detail="Payment record tidak ditemukan.")
    
    # Try to check real status from Midtrans
    if not payment_log.is_demo:
        try:
            import httpx
            import base64
            
            auth_string = base64.b64encode(f"{MIDTRANS_SERVER_KEY}:".encode()).decode()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{MIDTRANS_STATUS_URL}/{order_id}/status",
                    headers={"Authorization": f"Basic {auth_string}"},
                    timeout=10.0
                )
                if response.status_code == 200:
                    data = response.json()
                    payment_log.payment_status = data.get("transaction_status", payment_log.payment_status)
                    payment_log.midtrans_response = json.dumps(data)
                    
                    if payment_log.payment_status == "settlement":
                        trx = db.query(Transaksi).filter(Transaksi.id == payment_log.transaksi_id).first()
                        if trx and trx.status != "lunas":
                            trx.status = "lunas"
                            trx.metode_pembayaran = data.get("payment_type", "midtrans")
                    
                    db.commit()
        except:
            pass
    
    return {"status": "success", "data": PaymentRecord.model_validate(payment_log).model_dump(mode='json')}


# ══════════════════════════════════════════════════════════════
#  GET /payment/history — Riwayat pembayaran
# ══════════════════════════════════════════════════════════════

@router.get("/history")
def get_payment_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Ambil semua riwayat pembayaran."""
    logs = db.query(PaymentLog).order_by(PaymentLog.created_at.desc()).all()
    # Gunakan model_dump() untuk serialisasi manual jika tidak menggunakan response_model
    data = [PaymentRecord.model_validate(log).model_dump(mode='json') for log in logs]
    return {
        "status": "success",
        "data": data
    }


# ══════════════════════════════════════════════════════════════
#  POST /payment/simulate-success — Simulasi pembayaran berhasil (demo)
# ══════════════════════════════════════════════════════════════

class SimulatePaymentRequest(BaseModel):
    order_id: str

@router.post("/simulate-success")
def simulate_payment_success(
    payload: SimulatePaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Simulasi callback pembayaran berhasil (untuk testing/demo). NONAKTIF di production."""
    if MIDTRANS_IS_PRODUCTION:
        raise HTTPException(status_code=404, detail="Not found.")
    payment_log = db.query(PaymentLog).filter(PaymentLog.order_id == payload.order_id).first()
    if not payment_log:
        raise HTTPException(status_code=404, detail="Payment record tidak ditemukan.")
    
    payment_log.payment_status = "settlement"
    payment_log.payment_type = "demo_simulation"
    
    # Update transaksi status
    trx = db.query(Transaksi).filter(Transaksi.id == payment_log.transaksi_id).first()
    if trx:
        trx.status = "lunas"
        trx.metode_pembayaran = "midtrans"
    
    db.commit()
    db.refresh(payment_log)
    
    return {
        "status": "success",
        "message": f"Payment {payload.order_id} berhasil disimulasikan.",
        "data": PaymentRecord.model_validate(payment_log).model_dump(mode='json')
    }


# ══════════════════════════════════════════════════════════════
#  GET /payment/config — Get client config for frontend
# ══════════════════════════════════════════════════════════════

@router.get("/config")
def get_payment_config(current_user: User = Depends(get_current_user)):
    """Return Midtrans client configuration for frontend."""
    return {
        "status": "success",
        "data": {
            "client_key": MIDTRANS_CLIENT_KEY,
            "is_production": MIDTRANS_IS_PRODUCTION,
            "snap_url": "https://app.midtrans.com/snap/snap.js" if MIDTRANS_IS_PRODUCTION else "https://app.sandbox.midtrans.com/snap/snap.js",
            "enabled_payments": [
                "credit_card", "bca_va", "bni_va", "bri_va", "permata_va",
                "gopay", "shopeepay", "qris", "dana", "indomaret", "alfamart"
            ]
        }
    }
