import importlib
import os
import tempfile
import time
import unittest
from unittest.mock import patch
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        key = ec.generate_private_key(ec.SECP256R1())
        self.key = key
        public = (
            key.public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
        self.env = patch.dict(
            os.environ,
            {
                "NORX_DB": self.tmp.name + "/api.sqlite3",
                "NORX_DEV_AUTH": "0",
                "NORX_AUTO_WORKER": "1",
                "PRIVY_APP_ID": "test-app",
                "PRIVY_VERIFICATION_KEY": public,
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        import server

        self.server = importlib.reload(server)
        self.client = TestClient(self.server.app)

    def token(self, **changes):
        claims = {
            "sub": "did:privy:alice",
            "iss": "privy.io",
            "aud": "test-app",
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        }
        claims.update(changes)
        return {
            "Authorization": "Bearer " + jwt.encode(claims, self.key, algorithm="ES256")
        }

    def test_auth_and_public_browsing(self):
        self.assertEqual(self.client.get("/api/state").status_code, 200)
        self.assertEqual(self.client.get("/api/me").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/me", headers={"Authorization": "Bearer local-demo"}
            ).status_code,
            401,
        )
        for changes in (
            {"aud": "other-app"},
            {"exp": 0},
            {"iss": "wrong"},
            {"sub": "agent-01"},
        ):
            self.assertEqual(
                self.client.get("/api/me", headers=self.token(**changes)).status_code,
                401,
            )
        self.assertEqual(
            self.client.get("/api/me", headers=self.token()).json()["cash"], 10000
        )

    def test_backend_starts_simulation_and_launches_without_standalone_worker(self):
        with self.server.market.transaction() as db:
            db.execute("UPDATE meta SET value='0' WHERE key='next_launch_at'")
        with TestClient(self.server.app) as client:
            deadline = time.monotonic() + 5
            while True:
                state = client.get("/api/state").json()
                if state["simulation"]["running"] and state["total_coins"] == 8:
                    break
                if time.monotonic() > deadline:
                    self.fail(
                        "Backend did not start the simulation and launch a due batch"
                    )
                time.sleep(0.02)
            self.assertEqual(state["api_version"], 4)
            self.assertEqual(state["total_coins"], 8)
        from worker import worker_lock

        with worker_lock(self.server.market.path):
            pass  # API shutdown released ownership.

    def test_trade_flow_and_account_separation(self):
        h = self.token()
        self.client.get("/api/me", headers=h)
        q = self.client.post(
            "/api/quote",
            headers=h,
            json={"coin": "frog", "side": "buy", "budget": 50000000},
        )
        self.assertEqual(q.status_code, 200, q.text)
        body = {"quote_id": q.json()["id"], "request_id": "test-request"}
        r = self.client.post("/api/trade", headers=h, json=body)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(
            r.json(), self.client.post("/api/trade", headers=h, json=body).json()
        )
        bob = self.client.get("/api/me", headers=self.token(sub="did:privy:bob")).json()
        self.assertEqual(bob["cash"], 10000)
        self.assertEqual(bob["holdings"], {})
        self.assertEqual(
            self.client.post(
                "/api/trade", headers=self.token(sub="did:privy:bob"), json=body
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                "/api/quote",
                headers=h,
                json={"coin": "frog", "side": "buy", "budget": True},
            ).status_code,
            422,
        )
        self.assertTrue(self.client.get("/api/candles/frog").json())


if __name__ == "__main__":
    unittest.main()
