"""Users, password hashing and role based permissions."""
from __future__ import annotations

import hashlib
import hmac
import secrets

from ..db import Database, POSError, now

ROLES = ("admin", "manager", "cashier")

# Screen / action permissions per role.
PERMISSIONS = {
    "admin": {"*"},
    "manager": {
        "dashboard", "sales", "history", "returns", "products", "inventory",
        "customers", "suppliers", "purchases", "repairs", "warranty", "shifts",
        "expenses", "reports", "discount_override", "price_override", "customers_points",
        "return_override",
    },
    "cashier": {
        "dashboard", "sales", "history", "customers", "repairs", "warranty", "shifts",
    },
}

PBKDF2_ROUNDS = 200_000


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


def has_permission(user, perm: str) -> bool:
    allowed = PERMISSIONS.get(user["role"], set())
    return "*" in allowed or perm in allowed


def ensure_default_admin(db: Database):
    if db.scalar("SELECT COUNT(*) FROM users", default=0) == 0:
        create_user(db, "admin", "admin", "Administrator", "admin", must_change=True)


def create_user(db: Database, username: str, password: str, full_name: str = "",
                role: str = "cashier", must_change: bool = False, actor_id=None) -> int:
    username = username.strip()
    if not username:
        raise POSError("Username is required.")
    if role not in ROLES:
        raise POSError(f"Unknown role: {role}")
    if len(password) < 4:
        raise POSError("Password must be at least 4 characters.")
    if db.one("SELECT id FROM users WHERE username = ?", (username,)):
        raise POSError(f"User '{username}' already exists.")
    pw_hash, salt = hash_password(password)
    user_id = db.insert("users", {
        "username": username, "full_name": full_name.strip() or username,
        "password_hash": pw_hash, "salt": salt, "role": role,
        "must_change_password": int(must_change), "created_at": now(),
    })
    db.log(actor_id, "user.create", f"{username} ({role})")
    return user_id


def update_user(db: Database, user_id: int, full_name: str, role: str, active: bool, actor_id=None):
    if role not in ROLES:
        raise POSError(f"Unknown role: {role}")
    user = get_user(db, user_id)
    if user["role"] == "admin" and (role != "admin" or not active):
        others = db.scalar(
            "SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id != ?", (user_id,))
        if not others:
            raise POSError("You cannot remove the last active administrator.")
    db.update("users", user_id, {"full_name": full_name, "role": role, "active": int(active)})
    db.log(actor_id, "user.update", f"{user['username']} role={role} active={int(active)}")


def set_password(db: Database, user_id: int, new_password: str, must_change: bool = False, actor_id=None):
    if len(new_password) < 4:
        raise POSError("Password must be at least 4 characters.")
    pw_hash, salt = hash_password(new_password)
    db.update("users", user_id, {
        "password_hash": pw_hash, "salt": salt, "must_change_password": int(must_change)})
    db.log(actor_id, "user.password", f"user_id={user_id}")


def authenticate(db: Database, username: str, password: str):
    user = db.one("SELECT * FROM users WHERE username = ?", (username.strip(),))
    if not user or not user["active"] or not verify_password(password, user["password_hash"], user["salt"]):
        db.log(None, "login.failed", username)
        raise POSError("Invalid username or password.")
    db.log(user["id"], "login", user["username"])
    return user


def get_user(db: Database, user_id: int):
    user = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not user:
        raise POSError("User not found.")
    return user


def list_users(db: Database):
    return db.query("SELECT * FROM users ORDER BY username")
