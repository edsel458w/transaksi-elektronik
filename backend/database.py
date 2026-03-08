from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Ganti dengan URL database Anda
DATABASE_URL = "mysql+pymysql://root:@127.0.0.1:3306/pos_db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency untuk mendapatkan session database
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()