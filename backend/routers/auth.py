"""
routers/auth.py
Endpoint autentikasi: register, login, refresh token, logout, get profile.
"""
import re
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, field_validator
from jose import JWTError
from typing import Optional

from database import get_db
from models import User, RoleEnum
from core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from core.deps import get_current_user
from core.limiter import limiter

router = APIRouter(prefix="/auth", tags=["Auth"])

# Regex: minimal 8 karakter, mengandung huruf besar, huruf kecil, angka, dan simbol
_PW_PATTERN = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]).{8,128}$'
)

def _validate_password_complexity(v: str) -> str:
    if not _PW_PATTERN.match(v):
        raise ValueError(
            "Password harus minimal 8 karakter dan mengandung huruf besar, "
            "huruf kecil, angka, dan karakter spesial (!@#$%^&* dll)."
        )
    return v

# ── Schema request/response ──────────────────────────────────
class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: RoleEnum = RoleEnum.kasir  # default role = kasir

    @field_validator("password")
    @classmethod
    def pw_min_length(cls, v):
        if len(v) < 8:
            raise ValueError("Password minimal 8 karakter.")
        return v

    @field_validator("username")
    @classmethod
    def username_no_space(cls, v):
        if " " in v:
            raise ValueError("Username tidak boleh mengandung spasi.")
        return v.lower()

    @field_validator("password")
    @classmethod
    def pw_strength(cls, v):
        return _validate_password_complexity(v)

class LoginRequest(BaseModel):
    username: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    role: RoleEnum
    is_active: bool

    class Config:
        from_attributes = True

# ── Endpoint Register ────────────────────────────────────────
@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username sudah dipakai."
        )
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email sudah terdaftar."
        )

    user = User(
        username  = payload.username,
        email     = payload.email,
        hashed_pw = hash_password(payload.password),
        role      = RoleEnum.kasir,
        is_active = True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "status": "success",
        "message": f"User '{user.username}' berhasil didaftarkan.",
        "data": UserResponse.model_validate(user),
    }

# ── Endpoint Login ────────────────────────────────────────────
@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username.lower()).first()

    if not user or not verify_password(payload.password, user.hashed_pw):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah."
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun dinonaktifkan. Hubungi admin."
        )

    token_data = {"sub": str(user.id), "username": user.username, "role": user.role}
    access_token  = create_access_token(token_data)
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return {
        "status": "success",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user),
    }

# ── Endpoint Refresh Token ────────────────────────────────────
@router.post("/refresh")
@limiter.limit("10/minute")
def refresh_token(request: Request, payload: RefreshRequest, db: Session = Depends(get_db)):
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Refresh token tidak valid atau sudah kadaluarsa."
    )
    try:
        data = decode_token(payload.refresh_token)
        if data.get("type") != "refresh":
            raise exc
        user_id = data.get("sub")
    except JWTError:
        raise exc

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise exc

    token_data        = {"sub": str(user.id), "username": user.username, "role": user.role}
    access_token      = create_access_token(token_data)
    refresh_token_new = create_refresh_token({"sub": str(user.id)})

    return {
        "status": "success",
        "access_token": access_token,
        "refresh_token": refresh_token_new,
        "token_type": "bearer",
    }

# ── Endpoint Get Profile (butuh login) ───────────────────────
@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "status": "success",
        "data": UserResponse.model_validate(current_user),
    }

# ── Endpoint Daftar User (admin only) ────────────────────────
@router.get("/users")
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang bisa lihat daftar user.")

    users = db.query(User).all()
    return {
        "status": "success",
        "data": [UserResponse.model_validate(u) for u in users],
    }


class AdminCreateUserRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    role: RoleEnum
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def username_valid(cls, v):
        if " " in v or len(v) < 3 or len(v) > 50:
            raise ValueError("Username harus 3–50 karakter tanpa spasi.")
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError("Username hanya boleh mengandung huruf, angka, dan underscore.")
        return v.lower()

    @field_validator("password")
    @classmethod
    def pw_complexity(cls, v):
        return _validate_password_complexity(v)


class AdminUpdateUserRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[RoleEnum] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def pw_complexity(cls, v):
        if v is not None:
            return _validate_password_complexity(v)
        return v


@router.post("/users")
def create_user_by_admin(
    payload: AdminCreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang bisa membuat user.")

    if db.query(User).filter(User.username == payload.username.lower()).first():
        raise HTTPException(status_code=400, detail="Username sudah dipakai.")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email sudah dipakai.")

    user = User(
        username=payload.username.lower(),
        email=payload.email,
        hashed_pw=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "status": "success",
        "message": "User berhasil dibuat",
        "data": UserResponse.model_validate(user)
    }


@router.put("/users/{user_id}")
def update_user_by_admin(
    user_id: int,
    payload: AdminUpdateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang bisa mengubah user.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan.")

    if payload.username and payload.username.lower() != user.username:
        if db.query(User).filter(User.username == payload.username.lower()).first():
            raise HTTPException(status_code=400, detail="Username sudah dipakai.")
        user.username = payload.username.lower()

    if payload.email and payload.email != user.email:
        if db.query(User).filter(User.email == payload.email).first():
            raise HTTPException(status_code=400, detail="Email sudah dipakai.")
        user.email = payload.email

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password:
        user.hashed_pw = hash_password(payload.password)

    db.commit()
    db.refresh(user)
    return {
        "status": "success",
        "message": "User berhasil diupdate",
        "data": UserResponse.model_validate(user)
    }


@router.delete("/users/{user_id}")
def delete_user_by_admin(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang bisa menghapus user.")

    if current_user.id == user_id:
        raise HTTPException(status_code=400, detail="Tidak bisa menghapus akun sendiri.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User tidak ditemukan.")

    db.delete(user)
    db.commit()
    return {"status": "success", "message": "User berhasil dihapus."}


class ForgotPasswordRequest(BaseModel):
    username: str
    email: EmailStr
    new_password: str

    @field_validator("new_password")
    @classmethod
    def pw_complexity(cls, v):
        return _validate_password_complexity(v)


@router.post("/forgot-password")
@limiter.limit("3/minute")
def forgot_password(request: Request, payload: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.username == payload.username.lower(),
        User.email == payload.email,
        User.is_active == True,
    ).first()
    if user:
        user.hashed_pw = hash_password(payload.new_password)
        db.commit()
    return {
        "status": "success",
        "message": "Jika username dan email cocok, password telah direset. Silakan login."
    }
