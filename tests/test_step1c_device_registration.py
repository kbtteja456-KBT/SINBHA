"""
Tests for Step 1C Item 4:
Device registration platform declaration, friendly unique name requirement,
rejection of platform guessing from device ID or UA, and device renaming in Settings.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
import app.database as db

client = TestClient(app)

def test_register_device_rejects_missing_or_invalid_platform(setup_test_db):
    user = db.create_user("dev_plat_test@example.com", "Password123!", is_verified=True)
    user_id = user["id"]
    token = db.create_session(user_id)
    headers = {"Cookie": f"sinbha_session={token}"}

    # 1. Missing platform
    res1 = client.post(
        "/api/devices/register",
        headers=headers,
        json={"device_id": "dev_test_no_plat", "name": "My Laptop"}
    )
    assert res1.status_code == 400
    assert "platform must be explicitly declared" in res1.json()["detail"].lower()

    # 2. Invalid platform
    res2 = client.post(
        "/api/devices/register",
        headers=headers,
        json={"device_id": "dev_test_invalid_plat", "name": "My Smartwatch", "platform": "smartwatch"}
    )
    assert res2.status_code == 400
    assert "platform must be explicitly declared" in res2.json()["detail"].lower()

    # 3. Direct db call rejects invalid platform
    with pytest.raises(ValueError, match="platform must be explicitly declared"):
        db.create_or_register_device(
            user_id=user_id,
            device_id="dev_test_direct_invalid",
            name="My Console",
            platform="playstation"
        )


def test_register_device_rejects_missing_or_short_name(setup_test_db):
    user = db.create_user("dev_name_test@example.com", "Password123!", is_verified=True)
    user_id = user["id"]
    token = db.create_session(user_id)
    headers = {"Cookie": f"sinbha_session={token}"}

    # 1. Missing name
    res1 = client.post(
        "/api/devices/register",
        headers=headers,
        json={"device_id": "dev_test_no_name", "platform": "windows"}
    )
    assert res1.status_code == 400
    assert "device name must be explicitly declared" in res1.json()["detail"].lower()

    # 2. Single-char name
    res2 = client.post(
        "/api/devices/register",
        headers=headers,
        json={"device_id": "dev_test_short_name", "name": "x", "platform": "windows"}
    )
    assert res2.status_code == 400
    assert "device name must be explicitly declared" in res2.json()["detail"].lower()

    # 3. Direct db call rejects short name
    with pytest.raises(ValueError, match="device name must be explicitly declared"):
        db.create_or_register_device(
            user_id=user_id,
            device_id="dev_test_direct_short",
            name=" ",
            platform="windows"
        )


def test_server_does_not_guess_platform_from_prefix_or_user_agent(setup_test_db):
    """
    Step 1C Item 4: The server must never guess the platform from the device id
    prefix or the user agent, and must reject a registration that does not declare it.
    """
    user = db.create_user("no_guess_test@example.com", "Password123!", is_verified=True)
    user_id = user["id"]
    token = db.create_session(user_id)
    headers = {"Cookie": f"sinbha_session={token}"}

    # Device ID starts with 'android_' and User-Agent is Android/Dalvik, but platform is omitted
    headers = {
        "Cookie": f"sinbha_session={token}",
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 15; Pixel 8 Build/AP2A.240805.005)"
    }
    res = client.post(
        "/api/devices/register",
        headers=headers,
        json={"device_id": "android_999999", "name": "Pixel 8"}
    )
    assert res.status_code == 400
    assert "platform must be explicitly declared" in res.json()["detail"].lower()


def test_valid_registration_and_device_renaming(setup_test_db):
    """
    Step 1C Item 4: Valid registration with declared platform & unique friendly name,
    followed by renaming in Settings.
    """
    user = db.create_user("rename_test@example.com", "Password123!", is_verified=True)
    user_id = user["id"]
    token = db.create_session(user_id)
    headers = {"Cookie": f"sinbha_session={token}"}

    # 1. Register with declared Windows platform and computer name
    res = client.post(
        "/api/devices/register",
        headers=headers,
        json={"device_id": "win_comp_1", "name": "DESKTOP-ABC1234", "platform": "windows", "is_signup": True}
    )
    assert res.status_code == 200
    dev = res.json()["device"]
    assert dev["platform"] == "windows"
    assert dev["name"] == "DESKTOP-ABC1234"

    # 2. Register with declared Android platform and phone model
    res2 = client.post(
        "/api/devices/register",
        headers=headers,
        json={"device_id": "phone_comp_1", "name": "OnePlus CPH2413", "platform": "android", "is_signup": True}
    )
    assert res2.status_code == 200
    dev2 = res2.json()["device"]
    assert dev2["platform"] == "android"
    assert dev2["name"] == "OnePlus CPH2413"

    # 3. Rename device via explicit /api/devices/{id}/rename endpoint
    rename_res = client.post(
        f"/api/devices/win_comp_1/rename",
        headers=headers,
        json={"name": "Gaming Rig (Upstairs)"}
    )
    assert rename_res.status_code == 200
    renamed_dev = rename_res.json()["device"]
    assert renamed_dev["name"] == "Gaming Rig (Upstairs)"

    # Verify persistent update in database
    fetched = db.get_device_by_id(user_id, "win_comp_1")
    assert fetched["name"] == "Gaming Rig (Upstairs)"

    # Verify audit log recorded DEVICE_RENAMED
    logs = db.get_audit_logs(user_id, limit=10)
    rename_logs = [l for l in logs if l["action"] == "DEVICE_RENAMED"]
    assert len(rename_logs) >= 1
    assert "DESKTOP-ABC1234" in rename_logs[0]["details"]
    assert "Gaming Rig (Upstairs)" in rename_logs[0]["details"]
