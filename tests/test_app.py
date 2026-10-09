import os
import tempfile

tmp = tempfile.mkdtemp()
os.environ["HH_DB_PATH"] = os.path.join(tmp, "test.db")
os.environ["HH_UPLOAD_DIR"] = os.path.join(tmp, "uploads")
os.environ["ANTHROPIC_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def signup(name, email):
    r = client.post("/api/signup", json={"name": name, "email": email, "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_full_flow():
    farmer = signup("Rosa", "rosa@farm.test")
    buyer = signup("Sam", "sam@buyer.test")

    # duplicate email and bad login are refused
    assert client.post("/api/signup", json={"name": "x", "email": "rosa@farm.test", "password": "secret123"}).status_code == 400
    assert client.post("/api/login", json={"email": "rosa@farm.test", "password": "nope"}).status_code == 400
    assert client.post("/api/login", json={"email": "ROSA@farm.test", "password": "secret123"}).status_code == 200

    # AI draft falls back to the price guide without a key
    d = client.post("/api/ai/draft", data={"notes": "Honeycrisp apples picked yesterday"}, headers=farmer).json()
    assert d["category"] == "Fruit" and d["unit"] == "lb" and d["source"] == "builtin"

    # post a listing with a photo
    r = client.post("/api/listings", headers=farmer, data={
        "title": "Honeycrisp apples", "farm": "Maple Row", "description": "Sweet", "category": "Fruit",
        "unit": "lb", "price": "2.25", "qty": "10", "place": "Farm stand", "slots": "Sat 9-12, Sun 1-4"},
        files={"photo": ("a.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    lid = r.json()["id"]
    assert r.json()["slots"] == ["Sat 9-12", "Sun 1-4"]
    assert client.get(r.json()["photo_url"]).status_code == 200

    # anonymous can browse, cannot post
    assert len(client.get("/api/listings").json()) == 1
    assert client.post("/api/listings", data={}).status_code in (401, 422)

    # farmer can't reserve own; buyer can't over-reserve or pick a bad slot
    assert client.post("/api/reservations", headers=farmer, json={"listing_id": lid, "qty": 1, "slot": "Sat 9-12"}).status_code == 400
    assert client.post("/api/reservations", headers=buyer, json={"listing_id": lid, "qty": 11, "slot": "Sat 9-12"}).status_code == 400
    assert client.post("/api/reservations", headers=buyer, json={"listing_id": lid, "qty": 1, "slot": "Mon"}).status_code == 400

    r = client.post("/api/reservations", headers=buyer, json={"listing_id": lid, "qty": 4, "slot": "Sat 9-12"})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    assert client.get("/api/listings").json()[0]["qty_left"] == 6

    # farmer sees the order; buyer can't mark it done; farmer can
    assert client.get("/api/my/reservations", headers=farmer).json()["selling"][0]["buyer_name"] == "Sam"
    assert client.patch(f"/api/reservations/{rid}", headers=buyer, json={"status": "done"}).status_code == 403
    assert client.patch(f"/api/reservations/{rid}", headers=farmer, json={"status": "done"}).json()["status"] == "done"

    # cancel returns stock
    r2 = client.post("/api/reservations", headers=buyer, json={"listing_id": lid, "qty": 2, "slot": "Sun 1-4"}).json()
    client.patch(f"/api/reservations/{r2['id']}", headers=buyer, json={"status": "cancelled"})
    assert client.get("/api/listings").json()[0]["qty_left"] == 6

    # only the seller can edit; sold out hides it from the shop
    assert client.patch(f"/api/listings/{lid}", headers=buyer, json={"qty_left": 0}).status_code == 404
    client.patch(f"/api/listings/{lid}", headers=farmer, json={"qty_left": 0})
    assert client.get("/api/listings").json() == []

    # home page serves
    assert "Harvest" in client.get("/").text
