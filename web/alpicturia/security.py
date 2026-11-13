import hashlib
import hmac
import secrets
import time
import uuid
from fastapi import HTTPException


def uid():
    return uuid.uuid4().hex


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password):
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()
    return f"scrypt${salt.hex()}${value}"


def password_ok(password, stored):
    try:
        _, salt, expected = stored.split("$")
        value = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
        ).hex()
        return hmac.compare_digest(value, expected)
    except (ValueError, TypeError):
        return False


def limited(db, key, limit, window):
    now = time.time()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM rate_limits WHERE key=? AND expires<?", (key, now))
        conn.execute(
            "INSERT INTO rate_limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET hits=hits+1",
            (key, now + window),
        )
        hits = conn.execute(
            "SELECT hits FROM rate_limits WHERE key=?", (key,)
        ).fetchone()[0]
    if hits > limit:
        raise HTTPException(
            429,
            "Trop de tentatives. Réessayez plus tard.",
            headers={"Retry-After": str(window)},
        )


def audit(db, actor, action, target=None):
    db.run(
        "INSERT INTO audit(actor_id,action,target,created) VALUES(?,?,?,?)",
        (actor, action, target, time.time()),
    )


def enqueue(db, kind, ref_id):
    now = time.time()
    db.run(
        "INSERT OR IGNORE INTO jobs(id,kind,ref_id,available,created) VALUES(?,?,?,?,?)",
        (uid(), kind, ref_id, now, now),
    )


def issue_mail_token(db, user, kind, base_url):
    token = secrets.token_urlsafe(32)
    now = time.time()
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM tokens WHERE user_id=? AND kind=?", (user["id"], kind)
        )
        conn.execute(
            "INSERT INTO tokens VALUES(?,?,?,?)",
            (
                digest(token),
                user["id"],
                kind,
                now + (3600 if kind == "reset" else 86400),
            ),
        )
        label = (
            "Réinitialiser mon mot de passe"
            if kind == "reset"
            else "Confirmer mon adresse email"
        )
        conn.execute(
            "UPDATE mail SET status='expired',body='' WHERE user_id=? AND subject=? AND status='queued'",
            (user["id"], f"Alpicturia — {label}"),
        )
        link = f"{base_url}/account/{kind}#token={token}"
        conn.execute(
            "INSERT INTO mail(id,user_id,recipient,subject,body,available,created) VALUES(?,?,?,?,?,?,?)",
            (
                uid(),
                user["id"],
                user["email"],
                f"Alpicturia — {label}",
                f"{label}\n\n{link}\n\nSi vous n’êtes pas à l’origine de cette demande, ignorez ce message.",
                now,
                now,
            ),
        )
