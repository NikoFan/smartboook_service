import os
import bcrypt
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from . import models, database

# Создаём таблицы при запуске (если их нет)
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI()

# Зависимость для получения сессии БД
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserCreate(BaseModel):
    """
    Схема для ВХОДЯЩИХ данных при регистрации.
    FastAPI автоматически:
    - парсит JSON из тела запроса
    - проверяет, что есть username и password (и они строки)
    - отдаёт ошибку 422, если данные некорректны
    """
    username: str
    password: str


class UserResponse(BaseModel):
    """
    Схема для ИСХОДЯЩИХ данных (ответа).
    Определяет, какие поля будут возвращены клиенту.
    Скрывает пароль, возвращает только id и username.
    """
    id: int
    username: str

    class Config:
        # Разрешает Pydantic работать с объектами SQLAlchemy (ORM-моделями)
        from_attributes = True  # для SQLAlchemy 2.0+

# Хэширование пароля
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

# === ЭНДПОИНТ: ПРОВЕРКА РАБОТОСПОСОБНОСТИ ===
@app.get("/health")
def health():
    """
    Проверочный эндпоинт.
    Возвращает:
    - status: ok — сервер запущен
    - db_url_set: True/False — подключена ли БД
    - env: local или production — для отладки
    """
    return {
        "status": "ok",
        "db_url_set": bool(os.getenv("DATABASE_URL")),
        "env": "production" if os.getenv("RENDER") else "local"
    }


# === ЭНДПОИНТ: РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ ===
@app.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """
    Регистрирует нового пользователя.

    Параметры:
    - user: автоматически валидируется как UserCreate
    - db: сессия БД, полученная через Depends(get_db)

    Логика:
    1. Проверяем, не занят ли username
    2. Хэшируем пароль
    3. Сохраняем в БД
    4. Возвращаем UserResponse (без пароля!)
    """
    # Проверка уникальности логина
    existing = db.query(models.User).filter(models.User.user_login == user.user_login).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    # Хэшируем пароль (никогда не сохраняем оригинал!)
    hashed = hash_password(user.password)

    # Создаём ORM-объект
    db_user = models.User(username=user.username, hashed_password=hashed)

    # Сохраняем в БД
    db.add(db_user)
    db.commit()  # фиксируем транзакцию
    db.refresh(db_user)  # получаем user_id после INSERT

    # Возвращаем только то, что разрешено схемой UserResponse
    return db_user

# === ЭНДПОИНТ: ПОЛУЧЕНИЕ СПИСКА ПОЛЬЗОВАТЕЛЕЙ ===
@app.get("/users", response_model=list[UserResponse])
def get_users(db: Session = Depends(get_db)):
    """
    Возвращает список всех пользователей (без паролей!).
    Полезно для отладки или админки.
    """
    return db.query(models.User).all()