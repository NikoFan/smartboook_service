import os
import bcrypt
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
from datetime import *
import random
import smtplib
from email.mime.text import MIMEText
import threading

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

def send_verification_mail(code: str, goal_user: str) -> None:
    """
    Отправка кода подтверждения на почту через mail.ru
    """
    smtp_user = os.getenv("SMTP_NAME")
    smtp_password = os.getenv("SMTP_PASS")

    if not smtp_user or not smtp_password:
        print("SMTP_USER or SMTP_PASSWORD not set!")
        return  # Не падаем, если переменные не заданы

    try:
        # Используем SMTP mail.ru с портом 587 и STARTTLS
        with smtplib.SMTP("smtp.mail.ru", 465) as server:
            server.starttls()  # Включаем шифрование
            server.login(smtp_user, smtp_password)

            msg = MIMEText(f"Ваш код подтверждения: {code}")
            msg["Subject"] = "Подтверждение регистрации"
            msg["From"] = smtp_user
            msg["To"] = goal_user

            server.send_message(msg)
            print(f"Code {code} sent to {goal_user}")

    except Exception as e:
        print(f"Failed to send email to {goal_user}: {e}")
        # НЕ вызываем исключение — пусть регистрация завершится даже при ошибке отправки



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
    try:
        hashed = hash_password(data.user_password)
        code = str(random.randint(100000, 999999))
        pending = models.PendingUser(
            user_login=data.user_login,
            user_password=hashed,
            user_mail=data.user_mail,
            confirmation_code=code,
            expires_at=datetime.utcnow() + timedelta(minutes=10)
        )
        db.add(pending)
        db.commit()

        # Отвечаем СРАЗУ
        response = {
            "message": "Code sent to email",
            "code": f"{os.getenv("SMTP_NAME")} {data.user_mail}",
        }

        # Отправляем email в фоне
        def send_in_background():
            try:
                send_verification_mail(code=code, goal_user=data.user_mail)
            except Exception as e:
                print(f"Background email failed: {e}")

        threading.Thread(target=send_in_background, daemon=True).start()

        return response
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login or email already in use"
        )
    except Exception as e:
        db.rollback()
        # Логируем в продакшене, но не возвращаем клиенту
        print(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration temporarily unavailable"
        )


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


@app.post("/dev/reset-db", include_in_schema=False)
def reset_db():
    models.Base.metadata.drop_all(bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)
    return {"status": "DB reset"}

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



