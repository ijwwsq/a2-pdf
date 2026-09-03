"""Вход в сервис: одна учётная запись, пароль хранится хешем.

Пароль никогда не лежит в открытом виде: в переменной окружения задаётся
scrypt-хеш, полученный командой

    python -m a2pdf.auth

Сессия — подписанная кука: `имя|срок|подпись`, где подпись считается HMAC-SHA256
на секрете сервиса. Подделать её без секрета нельзя, а сервер не хранит состояние.

Переменные окружения:
    A2PDF_AUTH            off — вход отключён (для закрытого контура)
    A2PDF_USER            имя пользователя (по умолчанию admin)
    A2PDF_PASSWORD_HASH   scrypt-хеш пароля
    A2PDF_SECRET          секрет для подписи сессий
    A2PDF_SESSION_HOURS   срок жизни сессии, часов (по умолчанию 12)
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import ipaddress
import os
import secrets
import time
from collections import deque

COOKIE = "a2pdf_session"
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}
MAX_ATTEMPTS = 5          # неудачных попыток
ATTEMPT_WINDOW = 300      # за сколько секунд

_attempts: dict[str, deque] = {}


# --------------------------------------------------------------------------- #
# Пароль
# --------------------------------------------------------------------------- #

def hash_password(password: str, salt: bytes | None = None) -> str:
    """scrypt-хеш в виде scrypt$соль$хеш — его кладут в переменную окружения."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = stored.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode("utf-8"),
                                salt=bytes.fromhex(salt_hex), **SCRYPT)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


# --------------------------------------------------------------------------- #
# Настройки
# --------------------------------------------------------------------------- #

class Config:
    """Учётная запись и секрет сервиса, прочитанные из окружения."""

    def __init__(self) -> None:
        self.enabled = os.environ.get("A2PDF_AUTH", "on").strip().lower() not in (
            "off", "0", "false", "no")
        self.user = os.environ.get("A2PDF_USER", "admin").strip()
        self.password_hash = os.environ.get("A2PDF_PASSWORD_HASH", "").strip()
        self.hours = int(os.environ.get("A2PDF_SESSION_HOURS", 12))
        secret = os.environ.get("A2PDF_SECRET", "").strip()
        # без своего секрета сессии живут только до перезапуска — это заметно
        # в логах и не даёт молча работать с предсказуемым ключом
        self.secret = (secret or secrets.token_urlsafe(32)).encode("utf-8")
        self.secret_from_env = bool(secret)

    @property
    def configured(self) -> bool:
        """Нужно ли спрашивать вход: выключенная проверка тоже «настроена»."""
        return self.enabled and bool(self.password_hash)


def is_local(host: str | None) -> bool:
    """Локальный ли адрес: без настроенной учётки пускаем только с машины."""
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in ("localhost", "testclient")


# --------------------------------------------------------------------------- #
# Сессия
# --------------------------------------------------------------------------- #

def _sign(config: Config, payload: str) -> str:
    digest = hmac.new(config.secret, payload.encode("utf-8"),
                      hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def issue(config: Config, user: str) -> tuple[str, int]:
    """Возвращает значение куки и её срок жизни в секундах."""
    max_age = config.hours * 3600
    expires = int(time.time()) + max_age
    payload = f"{user}|{expires}"
    return f"{payload}|{_sign(config, payload)}", max_age


def validate(config: Config, cookie: str | None) -> str | None:
    """Имя пользователя, если кука цела и не просрочена."""
    if not cookie:
        return None
    try:
        user, expires, signature = cookie.rsplit("|", 2)
    except ValueError:
        return None
    payload = f"{user}|{expires}"
    if not hmac.compare_digest(signature, _sign(config, payload)):
        return None
    if not expires.isdigit() or int(expires) < time.time():
        return None
    return user if user == config.user else None


# --------------------------------------------------------------------------- #
# Защита от подбора
# --------------------------------------------------------------------------- #

def attempt_allowed(client: str) -> bool:
    now = time.monotonic()
    tries = _attempts.setdefault(client, deque())
    while tries and now - tries[0] > ATTEMPT_WINDOW:
        tries.popleft()
    return len(tries) < MAX_ATTEMPTS


def note_failure(client: str) -> None:
    _attempts.setdefault(client, deque()).append(time.monotonic())


def reset_attempts(client: str) -> None:
    _attempts.pop(client, None)


def check(config: Config, user: str, password: str) -> bool:
    """Сверяет логин и пароль. Хеш считается всегда — чтобы по времени ответа
    нельзя было понять, существует ли пользователь."""
    stored = config.password_hash or hash_password(secrets.token_hex(16))
    correct_password = verify_password(password, stored)
    correct_user = hmac.compare_digest(user.strip(), config.user)
    return bool(config.password_hash) and correct_user and correct_password


def main() -> None:
    """Генератор хеша для переменной окружения."""
    print("Пароль не отображается при вводе.")
    password = getpass.getpass("Пароль: ")
    repeat = getpass.getpass("Ещё раз: ")
    if password != repeat:
        raise SystemExit("Пароли не совпали")
    if len(password) < 10:
        raise SystemExit("Нужен пароль не короче 10 символов")
    print("\nДобавьте в окружение сервиса:\n")
    print(f'A2PDF_USER=admin')
    print(f'A2PDF_PASSWORD_HASH={hash_password(password)}')
    print(f'A2PDF_SECRET={secrets.token_urlsafe(32)}')


if __name__ == "__main__":
    main()
