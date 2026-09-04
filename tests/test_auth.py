"""Вход: хеши, подписанные сессии и защита от перебора."""
import time

import pytest

from a2pdf import auth


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv("A2PDF_AUTH", "on")
    monkeypatch.setenv("A2PDF_USER", "admin")
    monkeypatch.setenv("A2PDF_PASSWORD_HASH", auth.hash_password("длинный-пароль"))
    monkeypatch.setenv("A2PDF_SECRET", "секрет-для-подписи")
    return auth.Config()


def test_hash_is_salted():
    first = auth.hash_password("одинаковый")
    second = auth.hash_password("одинаковый")
    assert first != second
    assert auth.verify_password("одинаковый", first)
    assert auth.verify_password("одинаковый", second)


def test_wrong_password_rejected():
    stored = auth.hash_password("верный")
    assert not auth.verify_password("неверный", stored)


@pytest.mark.parametrize("stored", ["", "мусор", "scrypt$xx", "md5$aa$bb"])
def test_broken_hash_does_not_crash(stored):
    assert auth.verify_password("пароль", stored) is False


def test_check_requires_both_parts(config):
    assert auth.check(config, "admin", "длинный-пароль")
    assert not auth.check(config, "admin", "другой")
    assert not auth.check(config, "другой", "длинный-пароль")


def test_check_fails_without_configured_hash(monkeypatch):
    monkeypatch.setenv("A2PDF_PASSWORD_HASH", "")
    empty = auth.Config()
    assert not auth.check(empty, "admin", "что угодно")


def test_session_round_trip(config):
    cookie, max_age = auth.issue(config, "admin")
    assert max_age == config.hours * 3600
    assert auth.validate(config, cookie) == "admin"


@pytest.mark.parametrize("cookie", [
    None, "", "мусор", "admin|123", "admin|9999999999|неверная-подпись"])
def test_broken_cookie_rejected(config, cookie):
    assert auth.validate(config, cookie) is None


def test_expired_cookie_rejected(config):
    payload = f"admin|{int(time.time()) - 10}"
    cookie = f"{payload}|{auth._sign(config, payload)}"
    assert auth.validate(config, cookie) is None


def test_cookie_signed_by_other_secret_rejected(config, monkeypatch):
    cookie, _ = auth.issue(config, "admin")
    monkeypatch.setenv("A2PDF_SECRET", "другой-секрет")
    assert auth.validate(auth.Config(), cookie) is None


def test_cookie_for_other_user_rejected(config):
    cookie, _ = auth.issue(config, "чужой")
    assert auth.validate(config, cookie) is None


def test_attempts_are_limited():
    auth.reset_attempts("1.2.3.4")
    for _ in range(auth.MAX_ATTEMPTS):
        assert auth.attempt_allowed("1.2.3.4")
        auth.note_failure("1.2.3.4")
    assert not auth.attempt_allowed("1.2.3.4")
    auth.reset_attempts("1.2.3.4")
    assert auth.attempt_allowed("1.2.3.4")


@pytest.mark.parametrize("host, local", [
    ("127.0.0.1", True), ("::1", True), ("localhost", True),
    ("testclient", True), ("8.8.8.8", False), ("", False), (None, False)])
def test_is_local(host, local):
    assert auth.is_local(host) is local


def test_auth_off_switch(monkeypatch):
    for value in ("off", "0", "false", "no", "OFF"):
        monkeypatch.setenv("A2PDF_AUTH", value)
        assert auth.Config().enabled is False
    monkeypatch.setenv("A2PDF_AUTH", "on")
    assert auth.Config().enabled is True


def test_secret_generated_when_absent(monkeypatch):
    monkeypatch.delenv("A2PDF_SECRET", raising=False)
    config = auth.Config()
    assert config.secret and config.secret_from_env is False
