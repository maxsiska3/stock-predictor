# utils/auth.py — user registration, login, and Flask-Login integration

import re

import bcrypt
from flask_login import UserMixin

from utils.db import get_connection, utc_now_iso

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class User(UserMixin):
    """Flask-Login user object loaded from the users table."""

    def __init__(self, id, email, display_name):
        self.id = id
        self.email = email
        self.display_name = display_name

    @property
    def initial(self):
        name = (self.display_name or self.email or "?").strip()
        return name[0].upper()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _row_to_user(row) -> User:
    return User(id=row["id"], email=row["email"], display_name=row["display_name"])


def _validate_email(email):
    email = (email or "").strip().lower()
    if not email or not EMAIL_RE.match(email):
        raise AuthError("Enter a valid email address")
    return email


def _validate_password(password):
    if not password or len(password) < 8:
        raise AuthError("Password must be at least 8 characters")
    return password


def _validate_display_name(display_name, fallback_email):
    name = (display_name or "").strip()
    if not name:
        name = fallback_email.split("@")[0]
    if len(name) > 40:
        raise AuthError("Display name is too long")
    return name


def create_user(email, password, display_name=None):
    """
    Register a new user. Returns the created User.
    Raises AuthError if email is taken or validation fails.
    """
    email = _validate_email(email)
    password = _validate_password(password)
    display_name = _validate_display_name(display_name, email)
    password_hash = _hash_password(password)

    with get_connection() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise AuthError("An account with this email already exists")

        cur = conn.execute(
            "INSERT INTO users (email, password_hash, display_name, created_at) VALUES (?, ?, ?, ?)",
            (email, password_hash, display_name, utc_now_iso()),
        )
        conn.commit()
        user_id = cur.lastrowid

    return User(id=user_id, email=email, display_name=display_name)


def authenticate_user(email, password):
    """Verify credentials. Returns User on success, None on failure."""
    email = (email or "").strip().lower()
    if not email or not password:
        return None

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, email, password_hash, display_name FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if not row or not _check_password(password, row["password_hash"]):
        return None

    return _row_to_user(row)


def get_user_by_id(user_id):
    """Load a user by primary key — used by Flask-Login's user_loader."""
    if user_id is None:
        return None

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, email, display_name FROM users WHERE id = ?",
            (int(user_id),),
        ).fetchone()

    if not row:
        return None

    return _row_to_user(row)
