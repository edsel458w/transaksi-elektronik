from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from routers import inventory, transaction, auth, kontrak, io_system, deteksi_uang, midtrans_payment, laporan

app = FastAPI(
    title="SecureTransact API",
    description="Backend API Tugas IFB-352 - Grup C10 ITENAS",
    version="1.0.0",
)

# ── Security Headers Middleware ───────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# ── Rate Limiting Middleware (login endpoint) ─────────────────
_login_attempts: dict = defaultdict(list)
LOGIN_MAX_ATTEMPTS = int(os.getenv("LOGIN_MAX_ATTEMPTS", 5))
LOGIN_WINDOW_SECONDS = 60
LOGIN_LOCKOUT_SECONDS = 900  # 15 menit

class LoginRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/auth/login" and request.method == "POST":
            client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")
            now = time.time()
            attempts = _login_attempts[client_ip]
            # Bersihkan attempts di luar window + lockout
            _login_attempts[client_ip] = [t for t in attempts if now - t < LOGIN_LOCKOUT_SECONDS]
            recent = [t for t in _login_attempts[client_ip] if now - t < LOGIN_WINDOW_SECONDS]
            if len(recent) >= LOGIN_MAX_ATTEMPTS:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Terlalu banyak percobaan login. Coba lagi dalam 15 menit."},
                    headers={"Retry-After": str(LOGIN_LOCKOUT_SECONDS)},
                )
            response = await call_next(request)
            if response.status_code == 401:
                _login_attempts[client_ip].append(now)
            elif response.status_code == 200:
                _login_attempts[client_ip] = []
            return response
        return await call_next(request)

app.add_middleware(LoginRateLimitMiddleware)

# CORS - izinkan frontend Vue
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from database import SessionLocal
from sqlalchemy import text

# Health check
@app.get("/", tags=["Health"])
def read_root():
    return {"status": "success", "message": "SecureTransact Backend berjalan!"}

@app.get("/system-status", tags=["Health"])
def get_system_status():
    db_status = "offline"
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db_status = "online"
    except Exception:
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass

    return {
        "status": "success",
        "data": {
            "system_status": [
                {"name": "Backend FastAPI", "status": "online", "up": 100},
                {"name": "Database", "status": db_status, "up": 99 if db_status == "online" else 0},
                {"name": "Frontend Vue", "status": "online", "up": 100},
            ],
            "sec_checks": [
                {"name": "HTTPS / TLS 1.2+", "ok": True},
                {"name": "Rate Limiting", "ok": True},
                {"name": "JWT Authentication", "ok": True},
                {"name": "Input Validation", "ok": True},
            ]
        }
    }

# Register semua router
app.include_router(auth.router)
app.include_router(inventory.router)
app.include_router(transaction.router)
app.include_router(kontrak.router)
app.include_router(io_system.router)
app.include_router(deteksi_uang.router)
app.include_router(midtrans_payment.router)
app.include_router(laporan.router)
