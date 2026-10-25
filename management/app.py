import argparse
import getpass
import json
import os
import sqlite3
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from db import Database
from models import (DeviceCreate, DeviceShare, DeviceUpdate, Grant, GroupCreate, Login,
                    PasswordChange, Registration, TicketRequest, TicketVerify, UserCreate, UserUpdate)
from security import digest, hash_password, new_token, verify_password


def deny(status=403, message="Permission denied"):
    raise HTTPException(status, message)


def now():
    return int(time.time())


def audit(db, actor, action, target="", detail=""):
    db.execute("INSERT INTO audit_events(time,actor,action,target,detail) VALUES(?,?,?,?,?)",
               (now(), actor, action, str(target), detail))


def public_user(user):
    return {"id": user["id"], "name": user["name"], "display_name": user["display_name"],
            "is_admin": user["role"] == "admin", "status": int(user["enabled"]),
            "role": user["role"]}


def group_rows(db):
    rows = [dict(g) for g in db.execute("SELECT * FROM device_groups ORDER BY id")]
    by_id = {g["id"]: g for g in rows}
    for group in rows:
        names = [group["name"]]
        parent = group["parent_id"]
        while parent is not None:
            names.append(by_id[parent]["name"])
            parent = by_id[parent]["parent_id"]
        group["path"] = " / ".join(reversed(names))
    return rows


def permissions(db, user, group_id):
    if user["role"] == "admin":
        return {"view", "connect", "file_transfer", "terminal", "tunnel", "camera", "share"}
    rows = db.execute("""
        WITH RECURSIVE ancestors(id,parent_id) AS (
            SELECT id,parent_id FROM device_groups WHERE id=?
            UNION ALL SELECT g.id,g.parent_id FROM device_groups g JOIN ancestors a ON g.id=a.parent_id
        ) SELECT permissions FROM grants WHERE user_id=?
          AND group_id IN (SELECT id FROM ancestors) AND (expires_at IS NULL OR expires_at>?)
        """, (group_id, user["id"], now()))
    result = set()
    for row in rows:
        result.update(json.loads(row["permissions"]))
    return result


def device_permissions(db, user, device):
    allowed = permissions(db, user, device["group_id"])
    shares = db.execute("""SELECT s.permissions,u.* FROM device_shares s
        JOIN users u ON u.id=s.grantor_id WHERE s.device_id=? AND s.recipient_id=?
        AND u.enabled=1 AND (s.expires_at IS NULL OR s.expires_at>?)""",
                        (device["id"], user["id"], now())).fetchall()
    for share in shares:
        source = permissions(db, share, device["group_id"])
        if "share" in source:
            allowed.update(set(json.loads(share["permissions"])) & (source - {"share"}))
    return allowed


def require_row(db, table, key):
    # Table names are internal constants, never request values.
    row = db.execute(f"SELECT * FROM {table} WHERE id=?", (key,)).fetchone()
    if row is None:
        deny(404, "Not found")
    return row


def visible_devices(db, user):
    paths = {g["id"]: g["path"] for g in group_rows(db)}
    result = []
    for row in db.execute("SELECT * FROM devices WHERE enabled=1 ORDER BY name,id"):
        allowed = device_permissions(db, user, row)
        if "view" not in allowed:
            continue
        item = dict(row)
        del item["secret_hash"]
        item["permissions"] = sorted(allowed)
        item["can_share"] = "share" in permissions(db, user, row["group_id"])
        item["device_group_name"] = paths[row["group_id"]]
        item["info"] = {"device_name": row["name"], "os": row["platform"], "username": row["owner"]}
        item["status"] = 1
        item["user_name"] = ""
        result.append(item)
    return result


def page(items, request):
    try:
        current = int(request.query_params.get("current", 1))
        size = int(request.query_params.get("pageSize", 100))
    except ValueError:
        deny(422, "Invalid pagination")
    if current < 1 or not 1 <= size <= 200:
        deny(422, "Invalid pagination")
    return {"total": len(items), "data": items[(current-1)*size:current*size]}


def create_app(database_path=None):
    database = Database(database_path)
    app = FastAPI(title="RustDesk company management", version="0.1.0")
    app.state.database = database

    @app.exception_handler(HTTPException)
    async def http_error(_, exc):
        return JSONResponse({"error": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_, exc):
        # Do not reflect password or token fields from Pydantic's error input.
        return JSONResponse({"error": "Invalid request", "fields": [
            {"field": ".".join(map(str, e["loc"])), "message": e["msg"]} for e in exc.errors()
        ]}, status_code=422)

    @app.exception_handler(sqlite3.IntegrityError)
    async def conflict(_, exc):
        return JSONResponse({"error": "Conflicting record or invalid reference"}, status_code=409)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    def user_session(request: Request):
        token = request.headers.get("Authorization", "").removeprefix("Bearer ")
        with database.connect() as db:
            user = db.execute("""SELECT u.*,s.token_hash AS session_hash FROM users u
                JOIN sessions s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires_at>?
                AND u.enabled=1""", (digest(token), now())).fetchone()
        if user is None:
            deny(401, "Login expired or account disabled")
        return dict(user)

    def admin(user=Depends(user_session)):
        if user["role"] != "admin":
            deny()
        return user

    @app.get("/healthz")
    def health():
        with database.connect() as db:
            db.execute("SELECT 1")
        return {"status": "ok", "version": "0.1.0"}

    @app.post("/api/register", status_code=201)
    def register(body: Registration, request: Request):
        if os.environ.get("RDM_ALLOW_REGISTRATION", "1") != "1":
            deny(403, "Account registration is disabled; contact your administrator")
        ip = request.client.host if request.client else "unknown"
        attempt_key = "registration:" + ip
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_attempts WHERE time<?", (now()-900,))
            count = db.execute("SELECT COUNT(*) FROM login_attempts WHERE key=?", (attempt_key,)).fetchone()[0]
            if count >= 10:
                return JSONResponse({"error": "Too many registration attempts; retry in 15 minutes"}, status_code=429)
            db.execute("INSERT INTO login_attempts(key,time) VALUES(?,?)", (attempt_key, now()))
            if db.execute("SELECT 1 FROM users WHERE name=?", (body.username,)).fetchone():
                return JSONResponse({"error": "Username is already registered"}, status_code=409)
            user_id = db.execute(
                "INSERT INTO users(name,display_name,password_hash,role) VALUES(?,?,?,'member')",
                (body.username, body.display_name.strip() or body.username, hash_password(body.password)),
            ).lastrowid
            token = new_token("rd_session_")
            ttl = 8*60*60
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (digest(token), user_id, now()+ttl))
            audit(db, body.username, "user.register", user_id, ip)
            audit(db, body.username, "login", detail=ip)
            return {"type": "access_token", "access_token": token, "expires_in": ttl,
                    "user": public_user(require_row(db, "users", user_id)),
                    "service": "rustdesk-company-management"}

    @app.post("/api/login")
    def login(body: Login, request: Request):
        if body.type != "account":
            deny(400, "Only company accounts are supported")
        ip = request.client.host if request.client else "unknown"
        keys = ["ip:" + ip, "account:" + body.username.lower()]
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_attempts WHERE time<?", (now()-900,))
            counts = [db.execute("SELECT COUNT(*) FROM login_attempts WHERE key=?", (k,)).fetchone()[0]
                      for k in keys]
            if counts[0] >= 60 or counts[1] >= 10:
                return JSONResponse({"error": "Too many login attempts; retry in 15 minutes"}, status_code=429)
            user = db.execute("SELECT * FROM users WHERE name=?", (body.username,)).fetchone()
            if user is None or not user["enabled"] or not verify_password(body.password, user["password_hash"]):
                for key in keys:
                    db.execute("INSERT INTO login_attempts(key,time) VALUES(?,?)", (key, now()))
                audit(db, body.username, "login.denied", detail=ip)
                return JSONResponse({"error": "Invalid username or password"}, status_code=401)
            token = new_token("rd_session_")
            ttl = 8*60*60
            db.execute("DELETE FROM tickets WHERE expires_at<=?", (now(),))
            db.execute("DELETE FROM tickets WHERE session_hash IN (SELECT token_hash FROM sessions WHERE expires_at<=?)", (now(),))
            db.execute("DELETE FROM sessions WHERE expires_at<=?", (now(),))
            db.execute("INSERT INTO sessions VALUES(?,?,?)", (digest(token), user["id"], now()+ttl))
            db.execute("DELETE FROM login_attempts WHERE key=?", (keys[1],))
            audit(db, user["name"], "login", detail=ip)
            return {"type": "access_token", "access_token": token, "expires_in": ttl,
                    "user": public_user(user), "service": "rustdesk-company-management"}

    @app.post("/api/currentUser")
    def current_user(user=Depends(user_session)):
        return public_user(user)

    @app.post("/api/logout")
    def logout(user=Depends(user_session)):
        with database.connect() as db:
            db.execute("DELETE FROM tickets WHERE session_hash=?", (user["session_hash"],))
            db.execute("DELETE FROM sessions WHERE token_hash=?", (user["session_hash"],))
            audit(db, user["name"], "logout")
        return {}

    @app.get("/api/login-options")
    def login_options():
        return []

    @app.get("/api/users")
    def accessible_users(request: Request, user=Depends(user_session)):
        return page([], request)

    @app.get("/api/device-group/accessible")
    def accessible_groups(request: Request, user=Depends(user_session)):
        with database.connect() as db:
            all_groups = group_rows(db)
            by_id = {g["id"]: g for g in all_groups}
            visible_groups = set()
            for device in visible_devices(db, user):
                key = device["group_id"]
                while key is not None and key not in visible_groups:
                    visible_groups.add(key)
                    key = by_id[key]["parent_id"]
            groups = [{**g, "name": g["path"]} for g in all_groups
                      if g["id"] in visible_groups or "view" in permissions(db, user, g["id"])]
        return page(groups, request)

    @app.get("/api/peers")
    def peers(request: Request, user=Depends(user_session)):
        with database.connect() as db:
            return page(visible_devices(db, user), request)

    @app.get("/api/ab")
    def address_book(user=Depends(user_session)):
        with database.connect() as db:
            devices = visible_devices(db, user)
        return {"data": json.dumps({"tags": [], "peers": [
            {"id": d["id"], "alias": d["name"], "hostname": d["name"],
             "platform": d["platform"], "tags": [], "note": d["note"]} for d in devices]})}

    @app.post("/api/ab")
    def edit_address_book(user=Depends(user_session)):
        deny(403, "Company devices are managed by an administrator")

    @app.get("/api/admin/users")
    def users_list(user=Depends(admin)):
        with database.connect() as db:
            return [public_user(u) for u in db.execute("SELECT * FROM users ORDER BY id")]

    @app.post("/api/admin/users", status_code=201)
    def users_create(body: UserCreate, user=Depends(admin)):
        password_hash = hash_password(body.password)
        with database.connect() as db:
            key = db.execute("INSERT INTO users(name,display_name,password_hash,role) VALUES(?,?,?,?)",
                             (body.name, body.display_name, password_hash, body.role)).lastrowid
            audit(db, user["name"], "user.create", key)
            return public_user(require_row(db, "users", key))

    @app.patch("/api/admin/users/{user_id}")
    def users_update(user_id: int, body: UserUpdate, user=Depends(admin)):
        if user_id == user["id"] and not body.enabled:
            deny(409, "Cannot disable your own administrator account")
        with database.connect() as db:
            require_row(db, "users", user_id)
            db.execute("UPDATE users SET enabled=? WHERE id=?", (body.enabled, user_id))
            if not body.enabled:
                db.execute("DELETE FROM tickets WHERE session_hash IN (SELECT token_hash FROM sessions WHERE user_id=?)", (user_id,))
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            audit(db, user["name"], "user.enable" if body.enabled else "user.disable", user_id)
        return {}

    @app.post("/api/admin/users/{user_id}/password")
    def password_reset(user_id: int, body: PasswordChange, user=Depends(admin)):
        password_hash = hash_password(body.password)
        with database.connect() as db:
            require_row(db, "users", user_id)
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))
            db.execute("DELETE FROM tickets WHERE session_hash IN (SELECT token_hash FROM sessions WHERE user_id=?)", (user_id,))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            audit(db, user["name"], "user.password_reset", user_id)
        return {}

    @app.get("/api/admin/groups")
    def groups_list(user=Depends(admin)):
        with database.connect() as db:
            return group_rows(db)

    @app.post("/api/admin/groups", status_code=201)
    def groups_create(body: GroupCreate, user=Depends(admin)):
        with database.connect() as db:
            if body.parent_id is not None:
                parent = require_row(db, "device_groups", body.parent_id)
                if parent["scope"] != body.scope:
                    deny(422, "Child group must have the same internal/external scope as its parent")
            key = db.execute("INSERT INTO device_groups(name,parent_id,scope) VALUES(?,?,?)",
                             (body.name, body.parent_id, body.scope)).lastrowid
            audit(db, user["name"], "group.create", key)
            return dict(require_row(db, "device_groups", key))

    @app.delete("/api/admin/groups/{group_id}")
    def groups_delete(group_id: int, user=Depends(admin)):
        with database.connect() as db:
            require_row(db, "device_groups", group_id)
            for table, column in (("devices", "group_id"), ("device_groups", "parent_id"), ("grants", "group_id")):
                if db.execute(f"SELECT 1 FROM {table} WHERE {column}=?", (group_id,)).fetchone():
                    deny(409, "Move devices and remove child groups and grants before deleting this group")
            db.execute("DELETE FROM device_groups WHERE id=?", (group_id,))
            audit(db, user["name"], "group.delete", group_id)
        return {}

    @app.get("/api/admin/devices")
    def devices_list(user=Depends(admin)):
        with database.connect() as db:
            devices = [dict(d) for d in db.execute("SELECT * FROM devices ORDER BY name,id")]
            for device in devices:
                del device["secret_hash"]
            return devices

    @app.post("/api/admin/devices", status_code=201)
    def devices_create(body: DeviceCreate, user=Depends(admin)):
        secret = new_token("rd_device_")
        with database.connect() as db:
            require_row(db, "device_groups", body.group_id)
            db.execute("""INSERT INTO devices(id,name,group_id,asset_no,owner,location,platform,note,secret_hash)
                VALUES(?,?,?,?,?,?,?,?,?)""", (body.id, body.name, body.group_id, body.asset_no,
                                               body.owner, body.location, body.platform, body.note, digest(secret)))
            audit(db, user["name"], "device.create", body.id)
        return {"id": body.id, "device_token": secret}

    @app.patch("/api/admin/devices/{device_id}")
    def devices_update(device_id: str, body: DeviceUpdate, user=Depends(admin)):
        with database.connect() as db:
            old = require_row(db, "devices", device_id)
            require_row(db, "device_groups", body.group_id)
            db.execute("UPDATE devices SET group_id=?,enabled=? WHERE id=?", (body.group_id, body.enabled, device_id))
            if old["group_id"] != body.group_id or not body.enabled:
                db.execute("DELETE FROM device_shares WHERE device_id=?", (device_id,))
            db.execute("DELETE FROM tickets WHERE device_id=?", (device_id,))
            audit(db, user["name"], "device.update", device_id,
                  json.dumps({"from_group": old["group_id"], **body.model_dump()}))
        return {}

    @app.post("/api/admin/devices/{device_id}/rotate-token")
    def rotate_token(device_id: str, user=Depends(admin)):
        secret = new_token("rd_device_")
        with database.connect() as db:
            require_row(db, "devices", device_id)
            db.execute("UPDATE devices SET secret_hash=? WHERE id=?", (digest(secret), device_id))
            db.execute("DELETE FROM tickets WHERE device_id=?", (device_id,))
            audit(db, user["name"], "device.rotate_token", device_id)
        return {"id": device_id, "device_token": secret}

    @app.get("/api/admin/grants")
    def grants_list(user=Depends(admin)):
        with database.connect() as db:
            return [{**dict(g), "permissions": json.loads(g["permissions"])}
                    for g in db.execute("SELECT * FROM grants ORDER BY user_id,group_id")]

    @app.post("/api/admin/grants")
    def grants_save(body: Grant, user=Depends(admin)):
        if body.expires_at is not None and body.expires_at <= now():
            deny(422, "Grant expiry must be in the future")
        allowed = sorted(set(body.permissions) | {"view"})
        with database.connect() as db:
            require_row(db, "users", body.user_id)
            require_row(db, "device_groups", body.group_id)
            db.execute("INSERT INTO grants VALUES(?,?,?,?) ON CONFLICT(user_id,group_id) DO UPDATE SET permissions=excluded.permissions,expires_at=excluded.expires_at",
                       (body.user_id, body.group_id, json.dumps(allowed), body.expires_at))
            audit(db, user["name"], "grant.save", body.user_id, json.dumps(body.model_dump()))
        return {}

    @app.delete("/api/admin/grants/{user_id}/{group_id}")
    def grants_delete(user_id: int, group_id: int, user=Depends(admin)):
        with database.connect() as db:
            db.execute("DELETE FROM grants WHERE user_id=? AND group_id=?", (user_id, group_id))
            audit(db, user["name"], "grant.revoke", user_id, str(group_id))
        return {}

    @app.get("/api/admin/audit")
    def audit_list(before: int | None = None, user=Depends(admin)):
        with database.connect() as db:
            return [dict(e) for e in db.execute(
                "SELECT * FROM audit_events WHERE id<? ORDER BY id DESC LIMIT 200", (before or 2**63-1,))]

    @app.get("/api/device-shares/options/{device_id}")
    def share_options(device_id: str, user=Depends(user_session)):
        with database.connect() as db:
            device = require_row(db, "devices", device_id)
            allowed = permissions(db, user, device["group_id"])
            if not device["enabled"] or "share" not in allowed:
                deny(403, "Device sharing permission is required")
            return {"device_id": device_id, "name": device["name"],
                    "permissions": sorted(allowed - {"share"})}

    @app.get("/api/device-shares")
    def shares_list(device_id: str | None = None, user=Depends(user_session)):
        with database.connect() as db:
            rows = db.execute("""SELECT s.*,d.name AS device_name,d.group_id,d.enabled AS device_enabled,
                g.name AS grantor_name,r.name AS recipient_name,g.enabled AS grantor_enabled,
                g.role AS grantor_role,r.enabled AS recipient_enabled FROM device_shares s
                JOIN devices d ON d.id=s.device_id JOIN users g ON g.id=s.grantor_id
                JOIN users r ON r.id=s.recipient_id
                WHERE (? OR s.grantor_id=? OR s.recipient_id=?) AND (? IS NULL OR s.device_id=?)
                ORDER BY s.id DESC""", (user["role"] == "admin", user["id"], user["id"], device_id, device_id)).fetchall()
            result = []
            for row in rows:
                source = permissions(db, {"id": row["grantor_id"], "role": row["grantor_role"]}, row["group_id"])
                valid = (row["device_enabled"] and row["grantor_enabled"] and row["recipient_enabled"]
                         and (row["expires_at"] is None or row["expires_at"] > now()) and "share" in source)
                requested = json.loads(row["permissions"])
                result.append({"id": row["id"], "device_id": row["device_id"], "device_name": row["device_name"],
                    "grantor_name": row["grantor_name"], "recipient_name": row["recipient_name"],
                    "permissions": requested, "effective_permissions": sorted(set(requested) & source) if valid else [],
                    "expires_at": row["expires_at"], "active": bool(valid),
                    "can_revoke": user["role"] == "admin" or user["id"] in (row["grantor_id"], row["recipient_id"])})
            return result

    @app.post("/api/device-shares")
    def shares_save(body: DeviceShare, user=Depends(user_session)):
        if body.expires_at is not None and body.expires_at <= now():
            deny(422, "Share expiry must be in the future")
        requested = set(body.permissions) | {"view"}
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            device = require_row(db, "devices", body.device_id)
            allowed = permissions(db, user, device["group_id"])
            if not device["enabled"] or "share" not in allowed or not requested <= allowed:
                deny(403, "Cannot share this device or grant permissions you do not have")
            recipient = db.execute("SELECT * FROM users WHERE name=? AND enabled=1", (body.username,)).fetchone()
            if recipient is None:
                deny(404, "Recipient account is unavailable")
            if recipient["id"] == user["id"]:
                deny(422, "Choose another user to share with")
            db.execute("""INSERT INTO device_shares(device_id,grantor_id,recipient_id,permissions,expires_at)
                VALUES(?,?,?,?,?) ON CONFLICT(device_id,grantor_id,recipient_id)
                DO UPDATE SET permissions=excluded.permissions,expires_at=excluded.expires_at""",
                       (body.device_id, user["id"], recipient["id"], json.dumps(sorted(requested)), body.expires_at))
            row = db.execute("SELECT id FROM device_shares WHERE device_id=? AND grantor_id=? AND recipient_id=?",
                             (body.device_id, user["id"], recipient["id"])).fetchone()
            audit(db, user["name"], "share.save", body.device_id, json.dumps(body.model_dump()))
            return {"id": row["id"]}

    @app.delete("/api/device-shares/{share_id}")
    def shares_revoke(share_id: int, user=Depends(user_session)):
        with database.connect() as db:
            row = require_row(db, "device_shares", share_id)
            if user["role"] != "admin" and user["id"] not in (row["grantor_id"], row["recipient_id"]):
                deny()
            db.execute("DELETE FROM device_shares WHERE id=?", (share_id,))
            audit(db, user["name"], "share.revoke", row["device_id"], str(share_id))
        return {}

    @app.post("/api/enterprise/tickets", status_code=201)
    def tickets_issue(body: TicketRequest, user=Depends(user_session)):
        with database.connect() as db:
            device = db.execute("SELECT * FROM devices WHERE id=? AND enabled=1", (body.device_id,)).fetchone()
            if device is None or body.action not in device_permissions(db, user, device):
                audit(db, user["name"], "ticket.denied", body.device_id, body.action)
                return JSONResponse({"error": "Device unavailable or permission denied"}, status_code=403)
            ticket = new_token("rd_ticket_")
            db.execute("DELETE FROM tickets WHERE expires_at<=?", (now(),))
            db.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?,?,0)",
                       (digest(ticket), user["session_hash"], body.device_id, body.controller_id,
                        body.action, body.challenge, now()+30))
            audit(db, user["name"], "ticket.issue", body.device_id, body.action)
        return {"ticket": ticket, "expires_in": 30}

    @app.post("/api/enterprise/verify")
    def tickets_verify(body: TicketVerify, request: Request):
        secret = request.headers.get("Authorization", "").removeprefix("Bearer ")
        with database.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            device = db.execute("SELECT * FROM devices WHERE id=? AND enabled=1 AND secret_hash=?",
                                (body.device_id, digest(secret))).fetchone()
            if device is None:
                deny(401, "Invalid device credential")
            ticket = db.execute("SELECT * FROM tickets WHERE token_hash=?", (digest(body.ticket),)).fetchone()
            user = None
            if ticket is not None:
                user = db.execute("""SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id
                    WHERE s.token_hash=? AND s.expires_at>? AND u.enabled=1""",
                                  (ticket["session_hash"], now())).fetchone()
            valid = (ticket is not None and user is not None and not ticket["consumed"]
                     and ticket["expires_at"] > now()
                     and all(ticket[k] == getattr(body, k) for k in ("device_id", "controller_id", "action", "challenge"))
                     and body.action in device_permissions(db, user, device))
            if not valid:
                audit(db, "device:"+body.device_id, "connection.denied", body.device_id, body.action)
                return JSONResponse({"error": "Authorization expired, revoked or invalid"}, status_code=403)
            db.execute("UPDATE tickets SET consumed=1 WHERE token_hash=?", (digest(body.ticket),))
            db.execute("UPDATE devices SET last_seen=? WHERE id=?", (now(), body.device_id))
            audit(db, user["name"], "connection.authorized", body.device_id, body.action)
        return {"allowed": True}

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/", include_in_schema=False)
    def console():
        return FileResponse(static / "index.html")

    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["create-admin", "serve"])
    parser.add_argument("--username", default="admin")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=21114)
    args = parser.parse_args()
    if args.command == "create-admin":
        password = os.environ.get("RDM_BOOTSTRAP_PASSWORD") or getpass.getpass("Administrator password (12+ characters): ")
        body = UserCreate(name=args.username, display_name=args.username, password=password, role="admin")
        with Database().connect() as db:
            db.execute("INSERT INTO users(name,display_name,password_hash,role) VALUES(?,?,?,?)",
                       (body.name, body.display_name, hash_password(body.password), "admin"))
            audit(db, "bootstrap", "user.create", body.name)
        print("Administrator created. No default credentials are installed.")
    else:
        import uvicorn
        uvicorn.run(create_app(), host=args.host, port=args.port, proxy_headers=False)


if __name__ == "__main__":
    main()
