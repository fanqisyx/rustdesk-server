"""Exercise the built EXE over HTTP using a disposable database and random credentials."""
import argparse
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def smoke(executable):
    with tempfile.TemporaryDirectory(prefix="RustDesk management smoke ") as temporary:
        work = Path(temporary).resolve()
        assert work.is_relative_to(Path(tempfile.gettempdir()).resolve())
        environment = dict(os.environ, RDM_DATABASE=str(work / "data/management.sqlite3"),
                           RDM_BOOTSTRAP_PASSWORD=secrets.token_urlsafe(24), RDM_ALLOW_REGISTRATION="1")
        bootstrap = subprocess.run([str(executable), "create-admin", "--username", "admin"], cwd=work,
                                   env=environment, capture_output=True, timeout=60)
        if bootstrap.returncode:
            raise RuntimeError("Built administrator command failed: " + bootstrap.stderr.decode(errors="replace"))
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(path, method="GET", token="", body=None, expected=200):
            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = "Bearer " + token
            data = None if body is None else json.dumps(body).encode()
            query = urllib.request.Request(base + path, data=data, headers=headers, method=method)
            try:
                response = opener.open(query, timeout=10)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                payload = response.read()
                if response.status != expected:
                    raise AssertionError(f"Unexpected status for {path}: {response.status}, expected {expected}")
                return json.loads(payload) if "application/json" in response.headers.get("Content-Type", "") else payload

        with (work / "api.log").open("wb") as log:
            process = subprocess.Popen([str(executable), "serve", "--host", "127.0.0.1", "--port", str(port)],
                                       cwd=work, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                for attempt in range(60):
                    if process.poll() is not None:
                        raise RuntimeError("Built API exited during startup: " + (work / "api.log").read_text(errors="replace"))
                    try:
                        request("/healthz")
                        break
                    except OSError:
                        time.sleep(0.5)
                else:
                    raise TimeoutError("Built API did not become healthy")
                assert b"/static/app.js" in request("/")
                assert request("/static/app.js")
                admin = request("/api/login", "POST", body={
                    "username": "admin", "password": environment["RDM_BOOTSTRAP_PASSWORD"]})["access_token"]
                password = secrets.token_urlsafe(24)
                alice = request("/api/register", "POST", body={"username": "alice", "password": password,
                    "password_confirmation": password}, expected=201)["access_token"]
                assert request("/api/peers", token=alice)["data"] == []
                request("/api/admin/users", token=alice, expected=403)
                group = request("/api/admin/groups", "POST", admin,
                                {"name": "Internal", "scope": "internal"}, 201)
                device = request("/api/admin/devices", "POST", admin,
                                 {"id": "123456789", "name": "Test PC", "group_id": group["id"]}, 201)
                share = request("/api/device-shares", "POST", admin,
                                {"device_id": device["id"], "username": "alice", "permissions": ["connect"]})
                assert [p["id"] for p in request("/api/peers", token=alice)["data"]] == [device["id"]]
                details = {"device_id": device["id"], "controller_id": "987654321", "action": "connect",
                           "challenge": "smoke-connection-challenge"}
                ticket = request("/api/enterprise/tickets", "POST", alice, details, 201)["ticket"]
                assert request("/api/enterprise/verify", "POST", device["device_token"],
                               {**details, "ticket": ticket})["allowed"] is True
                request(f"/api/device-shares/{share['id']}", "DELETE", admin)
                assert request("/api/peers", token=alice)["data"] == []
                request("/api/enterprise/tickets", "POST", alice, details, 403)
                print("Built EXE passed: static UI, registration, default deny, sharing, tickets and revocation")
            finally:
                if process.poll() is None:
                    # A onefile EXE has a bootloader parent and an application child.
                    subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                                   capture_output=True, check=True, timeout=20)
                process.wait(timeout=15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, default=Path(__file__).resolve().parents[1] / "dist/native/rustdesk-management.exe")
    arguments = parser.parse_args()
    smoke(arguments.executable.resolve())
