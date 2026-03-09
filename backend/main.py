from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import inventory, transaction

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

@app.get("/test")
def read_test():
    return {"status": "success", "message": "Backend FastAPI berjalan! test"}

app.include_router(inventory.router)
app.include_router(transaction.router)
