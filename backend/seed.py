"""
seed.py
Jalankan sekali untuk:
  1. Buat semua tabel di database
  2. Isi user default (admin, kasir, manajer)

Cara pakai:
    cd backend
    python seed.py

Password admin diambil dari env var ADMIN_SEED_PASSWORD di .env.
Jika tidak di-set, password di-generate secara acak dan dicetak ke terminal.
"""
import os
import secrets
from dotenv import load_dotenv

load_dotenv()

from database import init_db, SessionLocal
from models import User, RoleEnum, Produk
from core.security import hash_password

def _get_or_generate(env_key: str, label: str) -> str:
    val = os.getenv(env_key)
    if val:
        return val
    generated = secrets.token_urlsafe(16)
    print(f"   [!] {env_key} tidak di-set → password '{label}' di-generate: {generated}")
    return generated

def seed():
    print("Membuat tabel...")
    init_db()
    print("Tabel berhasil dibuat.\n")

    db = SessionLocal()

    admin_pw   = _get_or_generate("ADMIN_SEED_PASSWORD",   "admin")
    kasir_pw   = _get_or_generate("KASIR_SEED_PASSWORD",   "kasir1")
    manajer_pw = _get_or_generate("MANAJER_SEED_PASSWORD", "manajer1")

    default_users = [
        {"username": "admin",    "email": "admin@securetransact.local",    "password": admin_pw,   "role": RoleEnum.admin},
        {"username": "kasir1",   "email": "kasir1@securetransact.local",   "password": kasir_pw,   "role": RoleEnum.kasir},
        {"username": "manajer1", "email": "manajer1@securetransact.local", "password": manajer_pw, "role": RoleEnum.manajer},
    ]

    print("Membuat user default...")
    created = []
    for u in default_users:
        existing = db.query(User).filter(User.username == u["username"]).first()
        if existing:
            print(f"   skip  -> {u['username']} (sudah ada)")
            continue
        user = User(
            username  = u["username"],
            email     = u["email"],
            hashed_pw = hash_password(u["password"]),
            role      = u["role"],
        )
        db.add(user)
        created.append(u)
        print(f"   ok    -> {u['username']} [{u['role']}]")

    # ── Sample produk ──────────────────────────────────────────
    sample_produk = [
        {"nama_produk": "Laptop Gaming ASUS ROG",       "harga": 14500000, "stok": 8},
        {"nama_produk": "Monitor LG 27\" IPS",          "harga": 4200000,  "stok": 12},
        {"nama_produk": "Keyboard Mechanical Keychron", "harga": 1250000,  "stok": 20},
        {"nama_produk": "Mouse Logitech MX Master",     "harga": 850000,   "stok": 5},
        {"nama_produk": "Headset Sony WH-1000XM5",      "harga": 4999000,  "stok": 6},
        {"nama_produk": "SSD Samsung 1TB NVMe",         "harga": 1350000,  "stok": 15},
    ]

    print("\nMengisi sample produk...")
    existing_count = db.query(Produk).count()
    if existing_count > 0:
        print(f"   skip  -> produk sudah ada ({existing_count} item)")
    else:
        for p in sample_produk:
            db.add(Produk(**p))
            print(f"   ok    -> {p['nama_produk']}")

    db.commit()
    db.close()

    print("\nSeeding selesai!")
    if created:
        print("\nCredential login (simpan baik-baik, tidak akan ditampilkan lagi):")
        for u in created:
            print(f"  {u['username']:<10} / {u['password']:<20} (role: {u['role']})")
        print("\nGanti password default segera setelah login pertama!")

if __name__ == "__main__":
    seed()