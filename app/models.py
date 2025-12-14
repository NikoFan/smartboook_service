from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from .database import Base

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
