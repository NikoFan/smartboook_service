import os
import bcrypt
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from . import models, database

# Создаём таблицы при запуске (если их нет)
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI()
# Создаём таблицы при запуске
@app.on_event("startup")
def on_startup():
    models.Base.metadata.create_all(bind=database.engine)

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
    user_login: str
    user_password: str


class UserResponse(BaseModel):
    """
    Схема для ИСХОДЯЩИХ данных (ответа).
    Определяет, какие поля будут возвращены клиенту.
    Скрывает пароль, возвращает только id и username.
    """
    user_id: int
    user_login: str

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

@app.get("/data_exist")
def health():
    return {
        "data": "exist!!!"
    }


# === ЭНДПОИНТ: РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ ===
@app.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    print(user.user_login)
    print(user.user_password)
    print(user.user_id)
    # Проверка уникальности
    existing = db.query(models.User).filter(models.User.user_login == user.user_login).first()
    if existing:
        raise HTTPException(status_code=400, detail="Login already taken")

    # Хэшируем пароль
    hashed = hash_password(user.user_password)  # ← было user.password

    # Создаём ORM-объект с правильными полями
    db_user = models.User(
        user_login=user.user_login,         # ← было username
        user_password=hashed                # ← было hashed_password
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# === ЭНДПОИНТ: ПОЛУЧЕНИЕ СПИСКА ПОЛЬЗОВАТЕЛЕЙ ===
@app.get("/users", response_model=list[UserResponse])
def get_users(db: Session = Depends(get_db)):
    """
    Возвращает список всех пользователей (без паролей!).
    Полезно для отладки или админки.
    """
    return db.query(models.User).all()