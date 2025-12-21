from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, BigInteger
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, autoincrement=True, primary_key=True, index=True)
    user_login = Column(String, nullable=False)
    user_password = Column(String, nullable=False)
    user_mail = Column(String, nullable=False)
    # Обратная связь: пользователь может иметь множество записей
    records = relationship("Records", back_populates="owner")


class Records(Base):
    __tablename__ = "records"

    record_id = Column(Integer, primary_key=True, index=True)
    record_name = Column(String, nullable=False)
    record_description = Column(String, nullable=False)
    user_id_fk = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    owner = relationship("User", back_populates="records")

# Таблица для хранения данных "пользователя на проверке"
class PendingUser(Base):
    __tablename__ = "pending_users"

    id = Column(Integer, primary_key=True, index=True)
    user_login = Column(String, unique=True)
    user_password = Column(String)  # уже хэшированный!
    user_mail = Column(String, unique=True)
    confirmation_code = Column(BigInteger)  # например, "123456"
    expires_at = Column(DateTime)       # через 10 минут удалить
    created_at = Column(DateTime, default=datetime.utcnow)