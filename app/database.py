import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    raise RuntimeError("❌ DATABASE_URL is not set! Check Render environment variables.")

# Исправление для Render (postgres:// → postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=1,          # только 1 активное подключение
    max_overflow=0,       # не пытаться создавать дополнительные
    pool_pre_ping=True,   # проверяет подключение перед использованием (полезно при таймаутах)
    pool_recycle=300      # пересоздаёт подключение каждые 5 минут (на случай таймаута idle)
)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()