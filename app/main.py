import os
import bcrypt
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from . import models, database

# Создаём таблицы при запуске (если их нет)
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI()
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
    user_mail: str


class UserResponse(BaseModel):
    """
    Схема для ИСХОДЯЩИХ данных (ответа).
    Определяет, какие поля будут возвращены клиенту.
    Скрывает пароль, возвращает только id и username.
    """
    user_id: int
    user_login: str
    user_mail: str

    class Config:
        # Разрешает Pydantic работать с объектами SQLAlchemy (ORM-моделями)
        from_attributes = True  # для SQLAlchemy 2.0+

class LoginRequest(BaseModel):
    """
    Схема для авторизации пользователя
    """
    user_login: str
    user_password: str


def hash_password(password: str) -> str:
    """
    Хеширование пароля
    :param password: первоначальная версия пароля
    :return: закодированная версия пользовательского пароля
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


@app.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """ Авторизация пользователя """
    user = db.query(models.User).filter(models.User.user_login == request.user_login).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid login or password")
    if not user or not bcrypt.checkpw(
        request.user_password.encode(), user.user_password.encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"user_id": user.user_id, "username": user.user_login, "mail": user.user_mail}


# === ЭНДПОИНТ: РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ ===
@app.post("/register", response_model=UserResponse)
def register(user: UserCreate, db: Session = Depends(get_db)):
    """
    Регистрация пользователя
    Проверка дублирования логина or почты

    Хеширование пароля
    Добавление пользователя в таблицу
    """
    print(user.user_login)
    print(user.user_password)
    print(user.user_mail)
    # Проверка уникальности
    check_login_duplicate = db.query(models.User).filter(models.User.user_login == user.user_login).first()
    if check_login_duplicate:
        raise HTTPException(status_code=400, detail="Login already taken")

    check_mail_duplicate = db.query(models.User).filter(models.User.user_mail == user.user_mail).first()
    if check_mail_duplicate:
        raise HTTPException(status_code=400, detail="Mail already taken")

    # Хэшируем пароль
    hashed = hash_password(user.user_password)  # ← было user.password

    # Создаём ORM-объект с правильными полями
    db_user = models.User(
        user_login=user.user_login,         # ← было username
        user_password=hashed,               # ← было hashed_password
        user_mail=user.user_mail
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user



# === GET ===
@app.get("/users", response_model=list[UserResponse])
def get_users(db: Session = Depends(get_db)):
    """
    Возвращает список всех пользователей (без паролей!).
    Полезно для отладки или админки.
    """
    return db.query(models.User).all()

@app.get("/health")
def health():
    """
    Проверка состояния сервера
    :return: JSON
    """
    return {
        "status": "ok",
        "db_url_set": bool(os.getenv("DATABASE_URL")),
        "env": "production" if os.getenv("RENDER") else "local"
    }


# === DELETE ===
# Очистка данных (уберу после тестирования)
@app.delete("/users/clear", tags=["dev"])
def clear_users(db: Session = Depends(get_db)):
    """
    Удаление записей из таблицы
    :return: JSON message
    """
    # Сначала удаляем записи (Records)
    db.query(models.Records).delete()
    # Потом — пользователей
    db.query(models.User).delete()
    db.commit() # Сохранение изменений
    return {"message": "All users and records deleted"}


@app.post("/dev/drop-tables", include_in_schema=False)
def drop_all_tables(db: Session = Depends(get_db)):
    """
    Удаляет ВСЕ таблицы, определённые в ваших моделях SQLAlchemy.
    Используйте ТОЛЬКО в разработке!
    """
    # Вариант 1: через metadata (рекомендуется)
    models.Base.metadata.drop_all(bind=db.get_bind())

    # Альтернатива: если связи мешают — дропаем вручную в правильном порядке
    # db.execute(text("DROP TABLE IF EXISTS records, users CASCADE;"))

    return {"status": "success", "message": "All tables dropped."}