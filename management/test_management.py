import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import create_app
from db import Database
from security import digest, hash_password


class ManagementTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app(str(Path(self.tmp.name) / "test.sqlite3"))
        self.db = self.app.state.database
        with self.db.connect() as db:
            db.execute("INSERT INTO users(name,display_name,password_hash,role) VALUES(?,?,?,?)",
                       ("admin", "Administrator", hash_password("admin-password-123"), "admin"))
        self.client = TestClient(self.app)
        self.admin = self.login("admin", "admin-password-123")
        self.member = self.client.post("/api/admin/users", headers=self.admin, json={
            "name": "alice", "display_name": "Alice", "password": "alice-password-123"
        }).json()
        self.alice = self.login("alice", "alice-password-123")
        self.internal = self.group("公司资产", "internal")
        self.child = self.group("上海", "internal", self.internal["id"])
        self.external = self.group("客户 A", "external")
        self.device = self.device_create("123456789", self.child["id"])
        self.other = self.device_create("987654321", self.external["id"])

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def login(self, username, password):
        response = self.client.post("/api/login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    def group(self, name, scope, parent=None):
        response = self.client.post("/api/admin/groups", headers=self.admin,
                                    json={"name": name, "scope": scope, "parent_id": parent})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def device_create(self, device_id, group):
        response = self.client.post("/api/admin/devices", headers=self.admin, json={
            "id": device_id, "name": "工作站 " + device_id, "group_id": group,
            "asset_no": "ASSET-" + device_id, "owner": "IT", "location": "上海办公室"
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def grant(self, allowed, group=None, expires_at=None):
        response = self.client.post("/api/admin/grants", headers=self.admin, json={
            "user_id": self.member["id"], "group_id": group or self.internal["id"],
            "permissions": allowed, "expires_at": expires_at
        })
        self.assertEqual(response.status_code, 200, response.text)

    def ticket_body(self, **changes):
        return {"device_id": self.device["id"], "controller_id": "111222333",
                "action": "connect", "challenge": "random-connection-challenge", **changes}

    def ticket(self, **changes):
        body = self.ticket_body(**changes)
        response = self.client.post("/api/enterprise/tickets", headers=self.alice, json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return {**body, "ticket": response.json()["ticket"]}

    def verify(self, ticket, credential=None):
        return self.client.post("/api/enterprise/verify", json=ticket, headers={
            "Authorization": "Bearer " + (credential or self.device["device_token"])
        })

    def sharing_member(self, name):
        response = self.client.post("/api/register", json={"username": name,
            "password": "sharing-password-123", "password_confirmation": "sharing-password-123"})
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        return result["user"], {"Authorization": "Bearer " + result["access_token"]}

    def shared_ticket(self, headers):
        body = self.ticket_body()
        response = self.client.post("/api/enterprise/tickets", headers=headers, json=body)
        self.assertEqual(response.status_code, 201, response.text)
        return {**body, "ticket": response.json()["ticket"]}

    def test_device_share_exposes_one_computer_and_only_the_selected_permissions(self):
        _, bob = self.sharing_member("bob")
        self.device_create("333444555", self.child["id"])
        self.grant(["connect", "file_transfer", "share"])
        response = self.client.post("/api/device-shares", headers=self.alice, json={
            "device_id": self.device["id"], "username": "BOB", "permissions": ["connect"]})
        self.assertEqual(response.status_code, 200, response.text)
        peers = self.client.get("/api/peers", headers=bob).json()["data"]
        self.assertEqual([peer["id"] for peer in peers], [self.device["id"]])
        self.assertEqual(peers[0]["permissions"], ["connect", "view"])
        self.assertFalse(peers[0]["can_share"])
        groups = self.client.get("/api/device-group/accessible", headers=bob).json()["data"]
        self.assertEqual({g["name"] for g in groups}, {"公司资产", "公司资产 / 上海"})
        address_book = json.loads(self.client.get("/api/ab", headers=bob).json()["data"])
        self.assertEqual([peer["id"] for peer in address_book["peers"]], [self.device["id"]])
        self.assertEqual(self.verify(self.shared_ticket(bob)).status_code, 200)
        self.assertEqual(self.client.post("/api/enterprise/tickets", headers=bob,
                                          json=self.ticket_body(action="file_transfer")).status_code, 403)
        self.assertEqual(self.client.post("/api/device-shares", headers=bob, json={
            "device_id": self.device["id"], "username": "alice", "permissions": ["connect"]}).status_code, 403)
        recipient = self.client.post("/api/currentUser", headers=bob).json()
        self.client.post("/api/admin/grants", headers=self.admin, json={
            "user_id": recipient["id"], "group_id": self.child["id"], "permissions": ["share"]})
        self.assertEqual(self.client.post("/api/device-shares", headers=bob, json={
            "device_id": self.device["id"], "username": "alice", "permissions": ["connect"]}).status_code, 403)

    def test_share_creation_and_management_require_explicit_delegation(self):
        _, bob = self.sharing_member("bob")
        _, outsider = self.sharing_member("outsider")
        body = {"device_id": self.device["id"], "username": "bob", "permissions": ["connect"]}
        self.grant(["connect"])
        self.assertEqual(self.client.post("/api/device-shares", headers=self.alice, json=body).status_code, 403)
        self.grant(["connect", "share"])
        self.assertEqual(self.client.post("/api/device-shares", headers=self.alice,
                                          json={**body, "permissions": ["terminal"]}).status_code, 403)
        self.assertEqual(self.client.post("/api/device-shares", headers=self.alice,
                                          json={**body, "permissions": ["share"]}).status_code, 422)
        for changes, status in [({"username": "alice"}, 422), ({"username": "missing"}, 404),
                                ({"expires_at": int(time.time())-1}, 422)]:
            self.assertEqual(self.client.post("/api/device-shares", headers=self.alice,
                                              json={**body, **changes}).status_code, status)
        saved = self.client.post("/api/device-shares", headers=self.alice, json=body).json()
        self.assertEqual(self.client.get("/api/device-shares", headers=outsider).json(), [])
        self.assertEqual(self.client.delete(f"/api/device-shares/{saved['id']}", headers=outsider).status_code, 403)
        self.assertEqual(self.client.get(f"/api/device-shares/options/{self.device['id']}", headers=bob).status_code, 403)
        self.assertEqual(self.client.get("/api/device-shares", headers=bob).json()[0]["grantor_name"], "alice")
        self.assertEqual(self.client.delete(f"/api/device-shares/{saved['id']}", headers=self.admin).status_code, 200)

    def test_share_revoke_expiry_and_source_permissions_are_checked_at_connection(self):
        _, bob = self.sharing_member("bob")
        self.grant(["connect", "share"])
        body = {"device_id": self.device["id"], "username": "bob", "permissions": ["connect"]}
        saved = self.client.post("/api/device-shares", headers=self.alice, json=body).json()
        pending = self.shared_ticket(bob)
        self.client.delete(f"/api/device-shares/{saved['id']}", headers=self.alice)
        self.assertEqual(self.verify(pending).status_code, 403)
        self.assertEqual(self.client.get("/api/peers", headers=bob).json()["total"], 0)
        self.client.post("/api/device-shares", headers=self.alice, json=body)
        pending = self.shared_ticket(bob)
        with self.db.connect() as db:
            db.execute("UPDATE device_shares SET expires_at=?", (int(time.time())-1,))
        self.assertEqual(self.verify(pending).status_code, 403)
        self.assertFalse(self.client.get("/api/device-shares", headers=bob).json()[0]["active"])
        self.client.post("/api/device-shares", headers=self.alice, json=body)
        pending = self.shared_ticket(bob)
        self.grant(["share"])
        self.assertEqual(self.verify(pending).status_code, 403)
        self.assertEqual(self.client.get("/api/peers", headers=bob).json()["data"][0]["permissions"], ["view"])
        self.grant(["connect"])
        self.assertEqual(self.client.get("/api/peers", headers=bob).json()["total"], 0)
        self.grant(["connect", "share"])
        pending = self.shared_ticket(bob)
        self.client.patch(f"/api/admin/users/{self.member['id']}", headers=self.admin, json={"enabled": False})
        self.assertEqual(self.verify(pending).status_code, 403)
        self.assertEqual(self.client.get("/api/peers", headers=bob).json()["total"], 0)

    def test_independent_grants_survive_share_removal_and_device_moves_remove_shares(self):
        user, bob = self.sharing_member("bob")
        body = {"device_id": self.device["id"], "username": "bob", "permissions": ["connect"]}
        saved = self.client.post("/api/device-shares", headers=self.admin, json=body).json()
        self.client.post("/api/admin/grants", headers=self.admin, json={
            "user_id": user["id"], "group_id": self.child["id"], "permissions": ["connect"]})
        self.client.delete(f"/api/device-shares/{saved['id']}", headers=bob)
        self.assertEqual(self.verify(self.shared_ticket(bob)).status_code, 200)
        self.client.delete(f"/api/admin/grants/{user['id']}/{self.child['id']}", headers=self.admin)
        self.client.post("/api/device-shares", headers=self.admin, json=body)
        pending = self.shared_ticket(bob)
        self.client.patch(f"/api/admin/devices/{self.device['id']}", headers=self.admin,
                          json={"group_id": self.external["id"], "enabled": True})
        self.assertEqual(self.verify(pending).status_code, 403)
        self.assertEqual(self.client.get("/api/device-shares", headers=bob).json(), [])
        self.assertEqual(self.client.get("/api/peers", headers=bob).json()["total"], 0)

    def test_schema_one_upgrade_preserves_existing_accounts_assets_and_grants(self):
        self.grant(["connect"])
        with self.db.connect() as db:
            db.execute("DROP TABLE device_shares")
            db.execute("PRAGMA user_version=1")
        upgraded = Database(self.db.path)
        with upgraded.connect() as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(self.client.get("/api/peers", headers=self.alice).json()["total"], 1)
        self.assertEqual(self.verify(self.ticket()).status_code, 200)
        self.grant(["connect", "share"])
        self.sharing_member("bob")
        self.assertEqual(self.client.post("/api/device-shares", headers=self.alice, json={
            "device_id": self.device["id"], "username": "bob", "permissions": ["connect"]}).status_code, 200)

    def test_default_deny_and_administrator_boundary(self):
        self.assertEqual(self.client.get("/api/peers", headers=self.alice).json()["data"], [])
        self.assertEqual(self.client.get("/api/admin/users", headers=self.alice).status_code, 403)
        self.assertEqual(self.client.get("/api/peers").status_code, 401)
        self.assertEqual(self.client.post("/api/enterprise/tickets", headers=self.alice,
                                          json=self.ticket_body()).status_code, 403)
        self.assertEqual(self.client.post("/api/login", json={"username": "alice", "password": "incorrect"}).status_code, 401)

    def test_inherited_scope_visibility_and_read_only_directory(self):
        self.grant(["view"])
        peers = self.client.get("/api/peers", headers=self.alice).json()
        self.assertEqual([p["id"] for p in peers["data"]], [self.device["id"]])
        self.assertEqual(peers["data"][0]["device_group_name"], "公司资产 / 上海")
        groups = self.client.get("/api/device-group/accessible", headers=self.alice).json()
        self.assertEqual(groups["total"], 2)
        self.assertEqual(self.client.get("/api/users", headers=self.alice).json()["total"], 0)
        book = json.loads(self.client.get("/api/ab", headers=self.alice).json()["data"])
        self.assertEqual([p["id"] for p in book["peers"]], [self.device["id"]])
        self.assertEqual(self.client.post("/api/ab", headers=self.alice, json={"data": "{}"}).status_code, 403)
        self.assertEqual(self.client.post("/api/enterprise/tickets", headers=self.alice,
                                          json=self.ticket_body()).status_code, 403)
        self.assertNotIn("secret", json.dumps(peers))

    def test_session_permissions_cannot_be_switched_or_replayed(self):
        self.grant(["connect"])
        ticket = self.ticket()
        self.assertEqual(self.verify({**ticket, "action": "terminal"}).status_code, 403)
        self.assertEqual(self.verify({**ticket, "controller_id": "attacker"}).status_code, 403)
        self.assertEqual(self.verify({**ticket, "challenge": "different-connection"}).status_code, 403)
        self.assertEqual(self.verify(ticket, self.other["device_token"]).status_code, 401)
        self.assertEqual(self.verify(ticket).json(), {"allowed": True})
        self.assertEqual(self.verify(ticket).status_code, 403)
        for action in ["terminal", "file_transfer", "tunnel", "camera"]:
            self.assertEqual(self.client.post("/api/enterprise/tickets", headers=self.alice,
                                              json=self.ticket_body(action=action)).status_code, 403)

    def test_revoke_expire_and_logout_invalidate_already_issued_tickets(self):
        self.grant(["connect"])
        ticket = self.ticket()
        self.client.delete(f"/api/admin/grants/{self.member['id']}/{self.internal['id']}", headers=self.admin)
        self.assertEqual(self.verify(ticket).status_code, 403)
        self.assertEqual(self.client.get("/api/peers", headers=self.alice).json()["total"], 0)
        self.grant(["connect"])
        ticket = self.ticket()
        with self.db.connect() as db:
            db.execute("UPDATE grants SET expires_at=?", (int(time.time()) - 1,))
        self.assertEqual(self.verify(ticket).status_code, 403)
        self.grant(["connect"])
        ticket = self.ticket()
        self.client.post("/api/logout", headers=self.alice)
        self.assertEqual(self.verify(ticket).status_code, 403)
        self.assertEqual(self.client.get("/api/peers", headers=self.alice).status_code, 401)

    def test_device_move_and_disable_change_visibility_and_authorization(self):
        self.grant(["connect"])
        ticket = self.ticket()
        self.assertEqual(self.client.patch(f"/api/admin/devices/{self.device['id']}", headers=self.admin,
                                           json={"group_id": self.external["id"], "enabled": True}).status_code, 200)
        self.assertEqual(self.verify(ticket).status_code, 403)
        self.assertEqual(self.client.get("/api/peers", headers=self.alice).json()["total"], 0)
        self.grant(["connect"], self.external["id"])
        self.assertEqual(self.verify(self.ticket()).status_code, 200)
        self.client.patch(f"/api/admin/devices/{self.device['id']}", headers=self.admin,
                          json={"group_id": self.external["id"], "enabled": False})
        self.assertEqual(self.client.post("/api/enterprise/tickets", headers=self.alice,
                                          json=self.ticket_body()).status_code, 403)

    def test_disable_user_and_reset_password_revoke_sessions(self):
        self.grant(["connect"])
        ticket = self.ticket()
        self.client.patch(f"/api/admin/users/{self.member['id']}", headers=self.admin, json={"enabled": False})
        self.assertEqual(self.verify(ticket).status_code, 403)
        self.assertEqual(self.client.get("/api/peers", headers=self.alice).status_code, 401)
        self.client.patch(f"/api/admin/users/{self.member['id']}", headers=self.admin, json={"enabled": True})
        self.alice = self.login("alice", "alice-password-123")
        self.client.post(f"/api/admin/users/{self.member['id']}/password", headers=self.admin,
                         json={"password": "new-password-123"})
        self.assertEqual(self.client.get("/api/peers", headers=self.alice).status_code, 401)
        self.login("alice", "new-password-123")
        self.assertEqual(self.client.patch("/api/admin/users/1", headers=self.admin,
                                          json={"enabled": False}).status_code, 409)

    def test_ticket_expiry_rotation_and_concurrent_single_use(self):
        self.grant(["connect"])
        ticket = self.ticket()
        with self.db.connect() as db:
            db.execute("UPDATE tickets SET expires_at=? WHERE token_hash=?", (int(time.time())-1, digest(ticket["ticket"])))
        self.assertEqual(self.verify(ticket).status_code, 403)
        rotated = self.client.post(f"/api/admin/devices/{self.device['id']}/rotate-token", headers=self.admin).json()
        ticket = self.ticket()
        self.assertEqual(self.verify(ticket).status_code, 401)
        self.device = rotated
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.verify(ticket).status_code, range(2)))
        self.assertEqual(sorted(results), [200, 403])

    def test_group_integrity_pagination_and_permission_union(self):
        self.assertEqual(self.client.post("/api/admin/groups", headers=self.admin, json={
            "name": "混入客户组", "parent_id": self.internal["id"], "scope": "external"
        }).status_code, 422)
        self.assertEqual(self.client.delete(f"/api/admin/groups/{self.internal['id']}", headers=self.admin).status_code, 409)
        self.grant(["view"])
        self.grant(["file_transfer"], self.child["id"])
        self.assertEqual(self.verify(self.ticket(action="file_transfer")).status_code, 200)
        self.assertEqual(self.client.get("/api/device-group/accessible?current=2&pageSize=1", headers=self.alice).json()["total"], 2)
        self.assertEqual(self.client.get("/api/peers?pageSize=0", headers=self.alice).status_code, 422)

    def test_audit_and_api_never_return_credentials(self):
        self.grant(["connect"])
        self.verify(self.ticket())
        for path in ["/api/admin/users", "/api/admin/devices", "/api/admin/audit", "/api/peers"]:
            response = self.client.get(path, headers=self.admin)
            self.assertEqual(response.status_code, 200)
            for secret in ["password_hash", "secret_hash", "admin-password-123", self.device["device_token"], "rd_session_"]:
                self.assertNotIn(secret, response.text)
        audit = self.client.get("/api/admin/audit", headers=self.admin).json()
        self.assertIn("connection.authorized", [a["action"] for a in audit])
        invalid = self.client.post("/api/admin/users", headers=self.admin,
                                   json={"name": "bad", "display_name": "Bad", "password": "secret"})
        self.assertEqual(invalid.status_code, 422)
        self.assertNotIn('"input"', invalid.text)
        self.assertNotIn('secret', invalid.text)

    def test_self_registration_signs_in_without_granting_device_or_admin_access(self):
        body = {"username": "new-member", "display_name": "新员工",
                "password": "new-member-password", "password_confirmation": "new-member-password"}
        response = self.client.post("/api/register", json=body)
        self.assertEqual(response.status_code, 201, response.text)
        result = response.json()
        self.assertEqual(result["service"], "rustdesk-company-management")
        self.assertEqual(result["user"]["role"], "member")
        self.assertFalse(result["user"]["is_admin"])
        headers = {"Authorization": "Bearer " + result["access_token"]}
        self.assertEqual(self.client.post("/api/currentUser", headers=headers).json()["name"], body["username"])
        for endpoint in ["/api/peers", "/api/device-group/accessible"]:
            self.assertEqual(self.client.get(endpoint, headers=headers).json()["total"], 0)
        self.assertEqual(self.client.get("/api/admin/users", headers=headers).status_code, 403)
        self.assertEqual(self.client.post("/api/admin/devices", headers=headers, json={
            "id": "555666777", "name": "Unauthorised", "group_id": self.internal["id"]}).status_code, 403)
        self.assertEqual(self.client.post("/api/enterprise/tickets", headers=headers,
                                          json=self.ticket_body()).status_code, 403)
        self.client.post("/api/logout", headers=headers)
        self.login(body["username"], body["password"])
        logs = self.client.get("/api/admin/audit", headers=self.admin).json()
        self.assertIn("user.register", [event["action"] for event in logs])
        self.assertNotIn(body["password"], json.dumps(logs))

    def test_self_registration_validates_input_and_duplicate_accounts_atomically(self):
        body = {"username": "self-user", "password": "self-user-password",
                "password_confirmation": "self-user-password"}
        for change in [{"password_confirmation": "different-password"}, {"password": "short"},
                       {"role": "admin"}, {"group_id": self.internal["id"]}, {"username": "bad name"}]:
            response = self.client.post("/api/register", json={**body, **change})
            self.assertEqual(response.status_code, 422, response.text)
            self.assertNotIn(body["password"], response.text)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.client.post("/api/register", json=body), range(2)))
        self.assertEqual(sorted(r.status_code for r in results), [201, 409])
        self.assertEqual(self.client.post("/api/register", json={**body, "username": "SELF-USER"}).status_code, 409)
        headers = self.login(body["username"], body["password"])
        self.assertEqual(self.client.post("/api/currentUser", headers=headers).json()["display_name"], body["username"])

    def test_self_registration_can_be_disabled_and_is_rate_limited(self):
        body = {"username": "limited-user", "password": "limited-user-password",
                "password_confirmation": "limited-user-password"}
        with patch.dict(os.environ, {"RDM_ALLOW_REGISTRATION": "0"}):
            self.assertEqual(self.client.post("/api/register", json=body).status_code, 403)
        self.assertEqual(self.client.post("/api/register", json=body).status_code, 201)
        for _ in range(9):
            self.assertEqual(self.client.post("/api/register", json=body).status_code, 409)
        self.assertEqual(self.client.post("/api/register", json={**body, "username": "another-user"}).status_code, 429)
        self.login(body["username"], body["password"])

    def test_login_rate_limit_and_console_headers(self):
        for _ in range(10):
            self.assertEqual(self.client.post("/api/login", json={"username": "nobody", "password": "wrong"}).status_code, 401)
        self.assertEqual(self.client.post("/api/login", json={"username": "nobody", "password": "wrong"}).status_code, 429)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.get("/static/app.js").status_code, 200)


if __name__ == "__main__":
    unittest.main()
