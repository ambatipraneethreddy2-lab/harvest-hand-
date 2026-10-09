"""Harvest Hand — local farm-to-buyer marketplace.

Run with:  uvicorn app.main:app --reload
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .pricing import CATEGORIES, UNITS, fallback_draft

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_PATH = Path(os.getenv("HH_DB_PATH", ROOT / "data" / "harvest.db"))
UPLOAD_DIR = Path(os.getenv("HH_UPLOAD_DIR", ROOT / "data" / "uploads"))
MAX_PHOTO_BYTES = 8 * 1024 * 1024
PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Harvest Hand")


# ---------- database ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
  pw_hash TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS listings (
  id TEXT PRIMARY KEY, seller_id TEXT NOT NULL REFERENCES users(id),
  title TEXT NOT NULL, farm TEXT NOT NULL, description TEXT, category TEXT NOT NULL,
  unit TEXT NOT NULL, price REAL NOT NULL, qty INTEGER NOT NULL, qty_left INTEGER NOT NULL,
  place TEXT NOT NULL, slots TEXT NOT NULL, photo TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reservations (
  id TEXT PRIMARY KEY, listing_id TEXT NOT NULL REFERENCES listings(id),
  buyer_id TEXT NOT NULL REFERENCES users(id), qty INTEGER NOT NULL, slot TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'waiting', created_at REAL NOT NULL
);
"""


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


with db() as c:
    c.executescript(SCHEMA)


# ---------- auth ----------
def hash_pw(pw: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return salt.hex() + ":" + digest.hex()


def check_pw(pw: str, stored: str) -> bool:
    salt_hex, _ = stored.split(":")
    return hmac.compare_digest(hash_pw(pw, bytes.fromhex(salt_hex)), stored)


def current_user(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "Please log in.")
    with db() as c:
        row = c.execute(
            "SELECT u.id, u.name, u.email FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?",
            (token,),
        ).fetchone()
    if not row:
        raise HTTPException(401, "Your session expired. Please log in again.")
    return dict(row)


def new_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with db() as c:
        c.execute("INSERT INTO sessions VALUES (?,?,?)", (token, user_id, time.time()))
    return token


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=6, max_length=200)


class LoginIn(BaseModel):
    email: str
    password: str


@app.post("/api/signup")
def signup(body: SignupIn):
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "Enter a valid email address.")
    uid = uuid.uuid4().hex
    with db() as c:
        if c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            raise HTTPException(400, "An account with that email already exists. Log in instead.")
        c.execute("INSERT INTO users VALUES (?,?,?,?,?)",
                  (uid, body.name.strip(), email, hash_pw(body.password), time.time()))
    return {"token": new_session(uid), "user": {"id": uid, "name": body.name.strip(), "email": email}}


@app.post("/api/login")
def login(body: LoginIn):
    with db() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),)).fetchone()
    if not row or not check_pw(body.password, row["pw_hash"]):
        raise HTTPException(400, "Email or password is wrong.")
    return {"token": new_session(row["id"]), "user": {"id": row["id"], "name": row["name"], "email": row["email"]}}


@app.post("/api/logout")
def logout(authorization: str = Header(default="")):
    with db() as c:
        c.execute("DELETE FROM sessions WHERE token=?", (authorization.removeprefix("Bearer ").strip(),))
    return {"ok": True}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return user


# ---------- listings ----------
def listing_out(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["slots"] = json.loads(d["slots"])
    d["photo_url"] = f"/uploads/{d['photo']}" if d["photo"] else None
    return d


async def save_photo(photo: UploadFile | None) -> tuple[str | None, bytes | None, str | None]:
    if not photo or not photo.filename:
        return None, None, None
    if photo.content_type not in PHOTO_TYPES:
        raise HTTPException(400, "Photo must be a JPG, PNG or WebP image.")
    data = await photo.read()
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(400, "Photo is too large (max 8 MB).")
    name = uuid.uuid4().hex + PHOTO_TYPES[photo.content_type]
    (UPLOAD_DIR / name).write_bytes(data)
    return name, data, photo.content_type


@app.get("/api/listings")
def list_listings(category: str | None = None, include_sold_out: bool = False):
    q = "SELECT * FROM listings WHERE 1=1"
    args: list = []
    if not include_sold_out:
        q += " AND qty_left > 0"
    if category and category != "All":
        q += " AND category=?"
        args.append(category)
    q += " ORDER BY created_at DESC LIMIT 500"
    with db() as c:
        return [listing_out(r) for r in c.execute(q, args)]


@app.get("/api/my/listings")
def my_listings(user=Depends(current_user)):
    with db() as c:
        rows = c.execute("SELECT * FROM listings WHERE seller_id=? ORDER BY created_at DESC", (user["id"],))
        return [listing_out(r) for r in rows]


@app.post("/api/listings")
async def create_listing(
    title: str = Form(..., max_length=80), farm: str = Form(..., max_length=80),
    description: str = Form("", max_length=600), category: str = Form(...), unit: str = Form(...),
    price: float = Form(..., ge=0, le=10000), qty: int = Form(..., ge=1, le=100000),
    place: str = Form(..., max_length=160), slots: str = Form(..., max_length=300),
    photo: UploadFile | None = File(None), user=Depends(current_user),
):
    if category not in CATEGORIES:
        raise HTTPException(400, "Pick a category from the list.")
    if unit not in UNITS:
        raise HTTPException(400, "Pick a unit from the list.")
    slot_list = [s.strip() for s in slots.split(",") if s.strip()][:8]
    if not slot_list:
        raise HTTPException(400, "Add at least one pickup time.")
    photo_name, _, _ = await save_photo(photo)
    lid = uuid.uuid4().hex
    with db() as c:
        c.execute(
            "INSERT INTO listings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (lid, user["id"], title.strip(), farm.strip(), description.strip(), category, unit,
             round(price, 2), qty, qty, place.strip(), json.dumps(slot_list), photo_name, time.time()),
        )
        return listing_out(c.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone())


class ListingPatch(BaseModel):
    qty_left: int | None = Field(default=None, ge=0)
    price: float | None = Field(default=None, ge=0)


@app.patch("/api/listings/{lid}")
def update_listing(lid: str, body: ListingPatch, user=Depends(current_user)):
    with db() as c:
        row = c.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
        if not row or row["seller_id"] != user["id"]:
            raise HTTPException(404, "Listing not found.")
        if body.qty_left is not None:
            c.execute("UPDATE listings SET qty_left=? WHERE id=?", (body.qty_left, lid))
        if body.price is not None:
            c.execute("UPDATE listings SET price=? WHERE id=?", (round(body.price, 2), lid))
        return listing_out(c.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone())


@app.delete("/api/listings/{lid}")
def delete_listing(lid: str, user=Depends(current_user)):
    with db() as c:
        row = c.execute("SELECT * FROM listings WHERE id=?", (lid,)).fetchone()
        if not row or row["seller_id"] != user["id"]:
            raise HTTPException(404, "Listing not found.")
        # Keep listings that have orders so buyers still see their history; just hide them.
        if c.execute("SELECT 1 FROM reservations WHERE listing_id=?", (lid,)).fetchone():
            c.execute("UPDATE listings SET qty_left=0 WHERE id=?", (lid,))
        else:
            c.execute("DELETE FROM listings WHERE id=?", (lid,))
            if row["photo"]:
                (UPLOAD_DIR / row["photo"]).unlink(missing_ok=True)
    return {"ok": True}


# ---------- reservations ----------
class ReserveIn(BaseModel):
    listing_id: str
    qty: int = Field(ge=1, le=100000)
    slot: str = Field(min_length=1, max_length=80)


RES_SELECT = """
SELECT r.*, l.title, l.unit, l.price, l.place, l.farm, l.seller_id, u.name AS buyer_name
FROM reservations r JOIN listings l ON l.id=r.listing_id JOIN users u ON u.id=r.buyer_id
"""


@app.post("/api/reservations")
def reserve(body: ReserveIn, user=Depends(current_user)):
    rid = uuid.uuid4().hex
    with db() as c:
        c.execute("BEGIN IMMEDIATE")  # lock so two buyers can't take the last items
        try:
            l = c.execute("SELECT * FROM listings WHERE id=?", (body.listing_id,)).fetchone()
            if not l:
                raise HTTPException(404, "That listing is gone.")
            if l["seller_id"] == user["id"]:
                raise HTTPException(400, "You can't reserve your own listing.")
            if body.slot not in json.loads(l["slots"]):
                raise HTTPException(400, "Pick one of the farm's pickup times.")
            if body.qty > l["qty_left"]:
                raise HTTPException(400, f"Only {l['qty_left']} {l['unit']} left.")
            c.execute("UPDATE listings SET qty_left=qty_left-? WHERE id=?", (body.qty, l["id"]))
            c.execute("INSERT INTO reservations VALUES (?,?,?,?,?,?,?)",
                      (rid, l["id"], user["id"], body.qty, body.slot, "waiting", time.time()))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        return dict(c.execute(RES_SELECT + " WHERE r.id=?", (rid,)).fetchone())


@app.get("/api/my/reservations")
def my_reservations(user=Depends(current_user)):
    with db() as c:
        buying = [dict(r) for r in c.execute(RES_SELECT + " WHERE r.buyer_id=? ORDER BY r.created_at DESC", (user["id"],))]
        selling = [dict(r) for r in c.execute(RES_SELECT + " WHERE l.seller_id=? ORDER BY r.created_at DESC", (user["id"],))]
    return {"buying": buying, "selling": selling}


class StatusIn(BaseModel):
    status: str


@app.patch("/api/reservations/{rid}")
def set_status(rid: str, body: StatusIn, user=Depends(current_user)):
    if body.status not in ("waiting", "done", "cancelled"):
        raise HTTPException(400, "Unknown status.")
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            r = c.execute(RES_SELECT + " WHERE r.id=?", (rid,)).fetchone()
            if not r or user["id"] not in (r["seller_id"], r["buyer_id"]):
                raise HTTPException(404, "Reservation not found.")
            if body.status == "done" and user["id"] != r["seller_id"]:
                raise HTTPException(403, "Only the farm can mark a pickup as done.")
            if body.status == "cancelled" and r["status"] == "waiting":
                c.execute("UPDATE listings SET qty_left=qty_left+? WHERE id=?", (r["qty"], r["listing_id"]))
            if r["status"] == "waiting":
                c.execute("UPDATE reservations SET status=? WHERE id=?", (body.status, rid))
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        return dict(c.execute(RES_SELECT + " WHERE r.id=?", (rid,)).fetchone())


# ---------- AI listing assistant ----------
AI_PROMPT = """You help small family farms near Mount Pleasant, Michigan sell produce directly to neighbors.
{photo_line}
Farmer's notes: {notes}
Write a short, honest listing. Don't invent claims like "organic" unless the notes say so.
Mention visible quality issues gently if there are any.
Suggest a fair direct-from-farm price in US dollars for mid-Michigan: usually a bit above wholesale and below grocery-store organic.
Reply with only JSON, no other text:
{{"title": str (max 40 chars), "description": str (1-2 sentences),
 "category": one of {cats}, "unit": one of {units},
 "price": number, "price_low": number, "price_high": number,
 "price_reason": str (one sentence), "freshness": str (one short storage tip for buyers)}}"""


def parse_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1])


@app.post("/api/ai/draft")
async def ai_draft(notes: str = Form("", max_length=600), photo: UploadFile | None = File(None),
                   user=Depends(current_user)):
    data, ctype = None, None
    if photo and photo.filename:
        if photo.content_type not in PHOTO_TYPES:
            raise HTTPException(400, "Photo must be a JPG, PNG or WebP image.")
        data, ctype = await photo.read(), photo.content_type
        if len(data) > 5 * 1024 * 1024:
            data = None  # too big for the AI; fall back to notes only
    if not notes.strip() and not data:
        raise HTTPException(400, "Add a photo or a few words about the produce.")

    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        out = fallback_draft(notes)
        out["source"] = "builtin"
        return out

    import anthropic

    content = []
    if data:
        content.append({"type": "image", "source": {"type": "base64", "media_type": ctype,
                                                     "data": base64.b64encode(data).decode()}})
    content.append({"type": "text", "text": AI_PROMPT.format(
        photo_line="The attached photo shows the produce for sale." if data else "",
        notes=notes.strip() or "(none)", cats=json.dumps(CATEGORIES), units=json.dumps(UNITS))})
    try:
        client = anthropic.AsyncAnthropic(api_key=key)
        msg = await client.messages.create(
            model=os.getenv("HH_MODEL", "claude-sonnet-5-5"), max_tokens=600,
            messages=[{"role": "user", "content": content}],
        )
        out = parse_json("".join(b.text for b in msg.content if b.type == "text"))
    except Exception as e:  # network, bad key, bad JSON → don't break the form
        out = fallback_draft(notes)
        out["source"] = "builtin"
        out["warning"] = f"AI unavailable ({type(e).__name__}); used built-in price guide."
        return out
    if out.get("category") not in CATEGORIES:
        out["category"] = "Other"
    if out.get("unit") not in UNITS:
        out["unit"] = "each"
    out["source"] = "llm"
    return out


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    return {"categories": CATEGORIES, "units": UNITS, "ai": bool(os.getenv("ANTHROPIC_API_KEY", "").strip())}


# ---------- static ----------
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")
