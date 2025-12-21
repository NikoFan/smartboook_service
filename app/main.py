import os
import bcrypt
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import *
import random

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


class RegisterRequest(BaseModel):
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

class ConfirmRequest(BaseModel):
    """
    Схема для запроса на подтверждение
    """
    email: str
    code: str


# === ФУНКЦИИ ===
def hash_password(password: str) -> str:
    """
    Хеширование пароля
    :param password: первоначальная версия пароля
    :return: закодированная версия пользовательского пароля
    """
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def generate_verification_code() -> int:
    """
    Метод генерации случайного кода для верификации пользователя
    :return: int()
    """
    return random.randint(100000, 999999)


def send_verification_mail(code: int, goal_user: str) -> None:
    """
    Метод отправки кода на почту пользователя
    :param code: отправляемый код
    :return: none
    """
    smtp_user = os.getenv("SMTP_NAME")
    smtp_password = os.getenv("SMTP_PASS")

    # Пример с отправкой через smtplib
    import smtplib
    from email.mime.text import MIMEText

    msg = MIMEText(f"Ваш код: {code}")
    msg["Subject"] = "Подтверждение регистрации"
    msg["From"] = smtp_user
    msg["To"] = goal_user

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)



# === POST ===
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
    return {"user_id": user.user_id, "user_login": user.user_login, "user_mail": user.user_mail}


@app.post("/register/init")
def init_registration(data: RegisterRequest, db: Session = Depends(get_db)):
    """ Инициализация процесса регистрации """
    # проверка уникальности...
    try:

        hashed = hash_password(data.user_password)
        code = generate_verification_code()
        pending = models.PendingUser(
            user_login=data.user_login,
            user_password=hashed,
            user_mail=data.user_mail,
            confirmation_code=str(code),
            expires_at=datetime.utcnow() + timedelta(minutes=10)
        )
        db.add(pending)
        db.commit()
        send_verification_mail(code=code, goal_user=data.user_mail) # Отправка кода на почту
        return {"message": "Code sent to email"}
    except Exception as e:
        return HTTPException(status_code=400, detail=e)


@app.post("/register/confirm")
def confirm_registration(confirm: ConfirmRequest, db: Session = Depends(get_db)):
    pending = db.query(models.PendingUser).filter(
        models.PendingUser.user_mail == confirm.email,
        models.PendingUser.confirmation_code == confirm.code
    ).first()

    if not pending or pending.expires_at < datetime.utcnow():
        raise HTTPException(400, "Invalid or expired code")

    # Переносим в основную таблицу
    user = models.User(
        user_login=pending.user_login,
        user_password=pending.user_password,
        user_mail=pending.user_mail
    )
    db.add(user)
    db.delete(pending)
    db.commit()
    return {"result": "success"}


# === ЭНДПОИНТ: РЕГИСТРАЦИЯ ПОЛЬЗОВАТЕЛЯ ===
@app.post("/register", response_model=UserResponse)
def register(user: RegisterRequest, db: Session = Depends(get_db)):
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
        user_login=user.user_login,  # ← было username
        user_password=hashed,  # ← было hashed_password
        user_mail=user.user_mail
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return {"user_id": user.user_id, "user_login": user.user_login, "user_mail": user.user_mail}


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
    db.commit()  # Сохранение изменений
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
