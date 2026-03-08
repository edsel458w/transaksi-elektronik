from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Inisialisasi Aplikasi
app = FastAPI(title="Core Backend API", description="API untuk Web Dashboard")

# Konfigurasi CORS agar Frontend (React/Vue) bisa menembak REST API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], # URL Frontend Anda
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoint dasar untuk test
@app.get("/")
def read_root():
    return {"status": "success", "message": "Backend FastAPI berjalan!"}

# --- Di bawah ini adalah contoh jika Anda mengimpor router terpisah ---
# from routers import auth, inventory, transactions, integrations
# 
# app.include_router(auth.router, prefix="/api/auth", tags=["Auth & Session"])
# app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory Logic"])
# app.include_router(transactions.router, prefix="/api/transactions", tags=["Transaction Management"])
# app.include_router(integrations.router, prefix="/api/integrations", tags=["Integration Handlers"])