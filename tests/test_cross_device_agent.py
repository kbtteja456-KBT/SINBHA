import os
import sys
import uuid
import pytest
from starlette.testclient import TestClient

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import tempfile
from app import database as db
from app.device_relay import relay_manager

temp_dir = tempfile.mkdtemp()
temp_db = os.path.join(temp_dir, "test_cross_device.db")
db.set_engine_url(f"sqlite:///{temp_db}")
db.init_db()

from app.main import app

client = TestClient(app)

@pytest.fixture
def auth_user():
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    user = db.create_user(email, "Password123!", is_18=True, agreed_terms=True)
    token = db.create_session(user["id"])
    return {"user": user, "token": token}

def test_version_check():
    res = client.get("/api/app/version-check")
    assert res.status_code == 200
    data = res.json()
    assert "SINBHA.apk" in data["download_url_android"]
    assert "SINBHA-Setup.exe" in data["download_url_desktop"]
    assert "android-v" in data["download_url_android"]
    assert "windows-v" in data["download_url_desktop"]

def test_notifications_sync_and_retrieval(auth_user):
    token = auth_user["token"]
    user_id = auth_user["user"]["id"]
    client.cookies.set("sinbha_session", token)

    payload = {
        "notifications": [
            {
                "app": "WhatsApp",
                "title": "Alex",
                "text": "Are you coming to dinner?",
                "timestamp": 1729876543210
            },
            {
                "app": "Gmail",
                "title": "Security Alert",
                "text": "New login detected",
                "timestamp": 1729876500000
            }
        ]
    }
    sync_res = client.post("/api/devices/notifications/sync", json=payload)
    assert sync_res.status_code == 200
    assert sync_res.json()["count"] == 2

    get_res = client.get("/api/devices/notifications")
    assert get_res.status_code == 200
    notifs = get_res.json()["notifications"]
    assert len(notifs) >= 2
    assert notifs[0]["app"] in ("WhatsApp", "Gmail")

def test_chat_read_notifications_intent(auth_user):
    token = auth_user["token"]
    client.cookies.set("sinbha_session", token)

    res = client.post("/api/chat", json={"message": "read my phone messages"})
    assert res.status_code == 200
    data = res.json()
    assert "Alex" in data["reply"] or "Notifications" in data["reply"] or "notifications" in data["reply"]

def test_chat_open_app_intent(auth_user):
    token = auth_user["token"]
    user_id = auth_user["user"]["id"]
    client.cookies.set("sinbha_session", token)

    # Register a trusted Windows laptop
    dev = db.create_or_register_device(user_id, "test_laptop_1", name="Test Laptop", platform="windows", password="Password123!")

    res = client.post("/api/chat", json={"message": "open whatsapp on my laptop"})
    assert res.status_code == 200
    data = res.json()
    assert "Done! Opened Whatsapp" in data["reply"] or "Opened Whatsapp" in data["reply"]

def test_chat_lock_workstation_intent(auth_user):
    token = auth_user["token"]
    user_id = auth_user["user"]["id"]
    client.cookies.set("sinbha_session", token)

    dev = db.create_or_register_device(user_id, "test_laptop_lock", name="My Laptop", platform="windows", password="Password123!")

    res = client.post("/api/chat", json={"message": "lock my laptop"})
    assert res.status_code == 200
    data = res.json()
    assert "Done! I've locked your My Laptop screen" in data["reply"]

def test_chat_battery_intent(auth_user):
    token = auth_user["token"]
    user_id = auth_user["user"]["id"]
    client.cookies.set("sinbha_session", token)

    dev = db.create_or_register_device(user_id, "test_phone_bat", name="My Phone", platform="android", password="Password123!")

    # Feed telemetry
    relay_manager.store_device_telemetry(user_id, dev["device_id"], {
        "battery": 87,
        "is_charging": True,
        "platform": "android"
    })

    res = client.post("/api/chat", json={"message": "check phone battery"})
    assert res.status_code == 200
    data = res.json()
    assert "87%" in data["reply"]
