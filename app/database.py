import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL is not set! Check Render environment variables.")

# Исправление для Render (postgres:// → postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_size=1,
    max_overflow=0,
    pool_pre_ping=True  # переподключается, если соединение "мертво"
)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()