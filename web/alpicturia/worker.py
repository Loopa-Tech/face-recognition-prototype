"""Durable single-host queue. Run separately from the HTTP process."""

import io
import json
import logging
import os
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
from .db import Database
from .security import uid

log = logging.getLogger("alpicturia.worker")
Image.MAX_IMAGE_PIXELS = 40_000_000


class FaceEngine:
    def encode(self, path):
        try:
            import face_recognition
        except (ImportError, SystemExit) as exc:
            raise RuntimeError(
                "Moteur facial indisponible : installer les dépendances IA."
            ) from exc
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1800, 1800))
            import numpy as np

            array = np.array(image)
        locations = face_recognition.face_locations(array, model="hog")
        return [
            encoding.tolist()
            for encoding in face_recognition.face_encodings(array, locations)
        ]


def validated_image(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("Formats acceptés : JPEG, PNG, WebP.")
            if image.width * image.height > 40_000_000 or min(image.size) < 64:
                raise ValueError("Image trop petite ou supérieure à 40 mégapixels.")
            image.verify()
    except (
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("Image illisible ou trop volumineuse.") from exc


def process_photo(db, photo, engine):
    path = db.root / photo["path"]
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        image.thumbnail((1600, 1600))
        draw = ImageDraw.Draw(image)
        text = "ALPICTURIA · APERÇU"
        for x in range(20, image.width, 360):
            for y in range(30, image.height, 240):
                draw.text(
                    (x, y), text, fill="white", stroke_width=2, stroke_fill="#222222"
                )
        preview = f"previews/{photo['id']}.jpg"
        image.save(db.root / preview, "JPEG", quality=82)
    encodings = engine.encode(path)
    with db.connect() as conn:
        conn.execute("DELETE FROM faces WHERE photo_id=?", (photo["id"],))
        conn.executemany(
            "INSERT INTO faces(photo_id,encoding) VALUES(?,?)",
            [(photo["id"], json.dumps(e)) for e in encodings],
        )
        conn.execute(
            "UPDATE photos SET status='ready',preview=?,face_count=?,error=NULL WHERE id=?",
            (preview, len(encodings), photo["id"]),
        )


def process_search(db, search, engine):
    if search["expires"] <= time.time():
        db.run(
            "UPDATE searches SET status='expired',path=NULL WHERE id=?", (search["id"],)
        )
        return
    encodings = engine.encode(db.root / search["path"])
    if len(encodings) != 1:
        raise ValueError(
            "Le selfie doit contenir exactement un visage. Reprenez une photo de face, bien éclairée."
        )
    reference = encodings[0]
    candidates = db.all(
        "SELECT f.photo_id,f.encoding FROM faces f JOIN photos p ON p.id=f.photo_id WHERE p.event_id=? AND p.status='ready'",
        (search["event_id"],),
    )
    found = {}
    for candidate in candidates:
        encoding = json.loads(candidate["encoding"])
        if len(encoding) != len(reference):
            continue
        distance = sum((a - b) ** 2 for a, b in zip(reference, encoding)) ** 0.5
        # Stricter than the desktop prototype's 0.6; must be calibrated with consented event data.
        if distance <= 0.48:
            found[candidate["photo_id"]] = min(
                distance, found.get(candidate["photo_id"], float("inf"))
            )
    with db.connect() as conn:
        conn.execute("DELETE FROM matches WHERE search_id=?", (search["id"],))
        conn.executemany(
            "INSERT INTO matches VALUES(?,?,?)",
            [(search["id"], p, d) for p, d in found.items()],
        )
        conn.execute(
            "UPDATE searches SET status='ready',error=NULL WHERE id=?", (search["id"],)
        )
    user = db.one("SELECT * FROM users WHERE id=?", (search["user_id"],))
    if user:
        now = time.time()
        db.run(
            "INSERT OR IGNORE INTO mail(id,user_id,recipient,subject,body,available,created) VALUES(?,?,?,?,?,?,?)",
            (
                "search-complete-" + search["id"],
                user["id"],
                user["email"],
                "Alpicturia — Votre recherche est terminée",
                f"Votre recherche est terminée : {len(found)} photo(s) candidate(s). Retrouvez les résultats dans votre espace Alpicturia.",
                now,
                now,
            ),
        )


def cleanup(db):
    now = time.time()
    for search in db.all(
        "SELECT id,path FROM searches WHERE expires<? AND status!=?", (now, "expired")
    ):
        if search["path"]:
            (db.root / search["path"]).unlink(missing_ok=True)
        with db.connect() as conn:
            conn.execute("DELETE FROM matches WHERE search_id=?", (search["id"],))
            conn.execute(
                "UPDATE searches SET status='expired',path=NULL WHERE id=?",
                (search["id"],),
            )
    with db.connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires<?", (now,))
        conn.execute("DELETE FROM tokens WHERE expires<?", (now,))
        conn.execute("DELETE FROM rate_limits WHERE expires<?", (now,))
        conn.execute("DELETE FROM metrics WHERE created<?", (now - 90 * 86400,))
        # Raw email bodies contain single-use links; remove promptly after delivery/expiry.
        conn.execute("UPDATE mail SET body='' WHERE created<?", (now - 86400,))


def send_mail(db):
    host = os.getenv("SMTP_HOST")
    if not host:
        return  # Explicitly queued, never pretend delivery.
    now = time.time()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        # Recover a mail lease if a previous worker stopped during SMTP delivery.
        conn.execute(
            "UPDATE mail SET status='queued' WHERE status='sending' AND available<?",
            (now,),
        )
        row = conn.execute(
            "SELECT * FROM mail WHERE status='queued' AND available<=? ORDER BY created LIMIT 1",
            (now,),
        ).fetchone()
        if not row:
            return
        row = dict(row)
        conn.execute(
            "UPDATE mail SET status='sending',attempts=attempts+1,available=? WHERE id=?",
            (now + 300, row["id"]),
        )
    try:
        if not row["body"] or row["created"] < now - 86400:
            db.run("UPDATE mail SET status='expired',body='' WHERE id=?", (row["id"],))
            return
        msg = EmailMessage()
        msg["Subject"] = row["subject"]
        msg["From"] = os.environ["SMTP_FROM"]
        msg["To"] = row["recipient"]
        msg["Message-ID"] = (
            f"<{row['id']}@{os.getenv('MAIL_MESSAGE_DOMAIN', 'alpicturia.local')}>"
        )
        msg.set_content(row["body"])
        port = int(os.getenv("SMTP_PORT", "587"))
        cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        with cls(
            host,
            port,
            timeout=20,
            **({"context": ssl.create_default_context()} if port == 465 else {}),
        ) as smtp:
            if port != 465:
                smtp.starttls(context=ssl.create_default_context())
            if os.getenv("SMTP_USER"):
                smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(msg)
        db.run(
            "UPDATE mail SET status='sent',body='',error=NULL WHERE id=?", (row["id"],)
        )
    except Exception:
        log.exception("Email delivery failed (id=%s)", row["id"])
        db.run(
            "UPDATE mail SET status=?,available=?,error='Échec SMTP' WHERE id=?",
            (
                "failed" if row["attempts"] >= 4 else "queued",
                now + min(3600, 60 * 2 ** row["attempts"]),
                row["id"],
            ),
        )


def run_once(db, engine=None):
    now = time.time()
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE jobs SET status='queued' WHERE status='running' AND lease_until<?",
            (now,),
        )
        row = conn.execute(
            "SELECT * FROM jobs WHERE status='queued' AND available<=? ORDER BY created LIMIT 1",
            (now,),
        ).fetchone()
        if not row:
            return False
        job = dict(row)
        conn.execute(
            "UPDATE jobs SET status='running',attempts=attempts+1,lease_until=? WHERE id=?",
            (now + 3600, job["id"]),
        )
    table = "photos" if job["kind"] == "photo" else "searches"
    item = db.one(f"SELECT * FROM {table} WHERE id=?", (job["ref_id"],))
    if not item:
        db.run("UPDATE jobs SET status='cancelled' WHERE id=?", (job["id"],))
        return True
    try:
        if item["status"] in ("ready", "expired"):
            db.run("UPDATE jobs SET status='done',error=NULL WHERE id=?", (job["id"],))
            return True
        db.run(f"UPDATE {table} SET status='running' WHERE id=?", (item["id"],))
        if job["kind"] == "photo":
            process_photo(db, item, engine or FaceEngine())
        else:
            process_search(db, item, engine or FaceEngine())
        db.run("UPDATE jobs SET status='done',error=NULL WHERE id=?", (job["id"],))
    except Exception as exc:
        log.exception("Job failed (id=%s)", job["id"])
        safe = (
            str(exc)
            if isinstance(exc, (ValueError, RuntimeError))
            else "Traitement impossible. Réessayez ou contactez le support."
        )
        db.run(
            f"UPDATE {table} SET status='failed',error=? WHERE id=?",
            (safe, job["ref_id"]),
        )
        db.run("UPDATE jobs SET status='failed',error=? WHERE id=?", (safe, job["id"]))
    finally:
        # Never retain the uploaded selfie after the engine has used it.
        if job["kind"] == "search" and item.get("path"):
            (db.root / item["path"]).unlink(missing_ok=True)
            db.run("UPDATE searches SET path=NULL WHERE id=?", (item["id"],))
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    db = Database()
    last_cleanup = 0
    while True:
        (db.root / "worker-heartbeat").write_text(str(time.time()))
        worked = run_once(db)
        send_mail(db)
        if time.time() - last_cleanup > 60:
            cleanup(db)
            last_cleanup = time.time()
        if not worked:
            time.sleep(1)


if __name__ == "__main__":
    main()
