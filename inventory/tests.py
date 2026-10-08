import base64
import io
import json
import tempfile
import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from .auth import resolve_identity, safe_next
from .models import Event, Item, Pairing


class InventoryTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        from pathlib import Path

        self.override = override_settings(MEDIA_ROOT=Path(self.tmp.name))
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.owner = User.objects.create_user(
            "owner", password="a very strong passphrase", is_staff=True
        )
        self.member = User.objects.create_user(
            "member", password="another long passphrase"
        )
        self.client.force_login(self.owner)

    def post(self, path, p, key=None, client=None):
        return (client or self.client).post(
            "/api/" + path,
            json.dumps(p),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
        )

    def tub(self, code):
        r = self.post("containers", {"code": code})
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["created"][0]["record"]

    def capture(self, c, title="unknown blue board", **kw):
        r = self.post("items", {"container_id": c["id"], "title": title, **kw})
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()

    def test_full_photo_workflow_history_and_tub_move(self):
        a, b = self.tub("B014"), self.tub("B015")
        f = io.BytesIO()
        Image.new("RGB", (20, 20), "blue").save(f, "PNG")
        data = base64.b64encode(f.getvalue()).decode()
        out = self.capture(a, "", photo=data)
        i = out["record"]
        self.assertEqual(i["title"], "Unidentified item")
        self.assertIsNone(i["quantity"])
        self.assertEqual(self.client.get("/api/media/" + i["photo"]).status_code, 200)
        for action, p in [
            (
                "edit",
                {
                    "title": "blue converter",
                    "aliases": "little blue board",
                    "metadata": {"model": "synthetic", "input_voltage": "unknown"},
                },
            ),
            ("take", {"destination": "Workbench"}),
            ("return", {"container_id": b["id"]}),
            ("missing", {}),
            ("move", {"container_id": a["id"]}),
        ]:
            out = self.post(
                "items/" + i["id"], {"action": action, "revision": i["revision"], **p}
            )
            self.assertEqual(out.status_code, 200, out.content)
            i = out.json()["record"]
        self.assertEqual(i["original"], "")
        self.assertEqual(i["status"], "stored")
        self.assertEqual(Event.objects.filter(entity_id=i["id"]).count(), 6)
        r = self.post(
            "containers/" + a["id"], {"revision": 1, "location": "West shelf"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Item.objects.get(pk=i["id"]).container.location, "West shelf")
        self.assertEqual(
            len(self.client.get("/api/items?q=blu+converter").json()["items"]), 1
        )

    def test_retry_stale_undo_and_atomic_bulk(self):
        a = self.tub("A1")
        key = str(uuid.uuid4())
        p = {"title": "bolts", "container_id": a["id"]}
        x = self.post("items", p, key)
        y = self.post("items", p, key)
        self.assertEqual(x.json(), y.json())
        self.assertEqual(Item.objects.count(), 1)
        self.assertEqual(
            self.post("items", {**p, "title": "different"}, key).status_code, 409
        )
        i = x.json()["record"]
        r = self.post("items/" + i["id"], {"action": "take", "revision": 1})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            self.post(
                "items/" + i["id"],
                {"action": "move", "revision": 1, "container_id": a["id"]},
            ).status_code,
            409,
        )
        self.assertEqual(self.post("undo/" + x.json()["event"], {}).status_code, 409)
        self.assertEqual(self.post("undo/" + r.json()["event"], {}).status_code, 200)
        j = self.capture(a)["record"]
        r = self.post(
            "bulk",
            {
                "action": "used",
                "items": [
                    {"id": j["id"], "revision": 1},
                    {"id": i["id"], "revision": 1},
                ],
            },
        )
        self.assertEqual(r.status_code, 409)
        self.assertEqual(Item.objects.get(pk=j["id"]).status, "stored")

    def test_shared_household_roles_and_splits(self):
        a, b = self.tub("A1"), self.tub("A2")
        member = Client()
        member.force_login(self.member)
        self.assertEqual(len(member.get("/api/containers").json()["containers"]), 2)
        self.assertEqual(member.get("/api/export").status_code, 403)
        self.assertEqual(member.get("/api/users").status_code, 403)
        i = self.capture(a, quantity=10)["record"]
        r = self.post(
            "items/" + i["id"],
            {"revision": 1, "action": "split", "quantity": 3, "container_id": b["id"]},
            client=member,
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(
            sorted(Item.objects.values_list("quantity", flat=True)), [3, 7]
        )
        self.assertEqual(Event.objects.filter(action="split").get().actor, self.member)
        u = self.capture(a)["record"]
        self.assertEqual(
            self.post(
                "items/" + u["id"],
                {
                    "revision": 1,
                    "action": "split",
                    "quantity": 1,
                    "container_id": b["id"],
                },
            ).status_code,
            400,
        )
        self.post(
            "items/" + u["id"],
            {
                "revision": 1,
                "metadata": {
                    "serial": "SYNTHETIC-1",
                    "model": "sensor",
                    "installed_location": "Greenhouse",
                    "test_status": "untested",
                },
            },
        )
        self.post("items/" + u["id"], {"revision": 2, "action": "take"})
        self.assertEqual(Item.objects.get(pk=u["id"]).status, "in_use")

    def test_access_csrf_media_and_tokens(self):
        anon = Client(enforce_csrf_checks=True)
        for path in (
            "items",
            "containers",
            "export",
            "media/" + "a" * 64 + ".jpg",
            "users",
        ):
            self.assertEqual(anon.get("/api/" + path).status_code, 401)
        anon.force_login(self.owner)
        self.assertEqual(
            self.post("containers", {"code": "X1"}, client=anon).status_code, 403
        )
        token = self.post("tokens", {"label": "test", "write": False}).json()["token"]
        c = Client()
        self.assertEqual(
            c.get("/api/items", HTTP_AUTHORIZATION="Bearer " + token).status_code, 200
        )
        self.assertEqual(
            c.post(
                "/api/items",
                "{}",
                content_type="application/json",
                HTTP_AUTHORIZATION="Bearer " + token,
            ).status_code,
            403,
        )

    def test_handoff_is_scoped_expiring_consumed_and_revocable(self):
        self.tub("B014")
        p = self.post("pairings", {"installation": "one", "label": "phone"}).json()

        def send():
            return Client().post(
                "/api/handoff/" + p["id"],
                json.dumps({"code": "B014"}),
                content_type="application/json",
                HTTP_AUTHORIZATION="Bearer " + p["credential"],
            )

        self.assertEqual(send().status_code, 200)
        member = Client()
        member.force_login(self.member)
        self.assertIsNone(
            self.post("consume", {"installation": "one"}, client=member).json()["code"]
        )
        self.assertIsNone(self.post("consume", {"installation": "two"}).json()["code"])
        self.assertEqual(
            self.post("consume", {"installation": "one"}).json()["code"], "B014"
        )
        self.assertIsNone(self.post("consume", {"installation": "one"}).json()["code"])
        send()
        Pairing.objects.update(expires=timezone.now() - timedelta(seconds=1))
        self.assertIsNone(self.post("consume", {"installation": "one"}).json()["code"])
        self.post("pairings", {"revoke": p["id"]})
        self.assertEqual(send().status_code, 403)

    @override_settings(OIDC_ISSUER="https://id.example.com/application/o/stash/")
    def test_identity_linking_and_groups(self):
        info = {
            "iss": "https://id.example.com/application/o/stash/",
            "sub": "first",
            "email": "owner@example.com",
            "groups": ["stash-members"],
        }
        u = resolve_identity(info)
        self.assertFalse(u.is_staff)
        u2 = resolve_identity({**info, "sub": "second"})
        self.assertNotEqual(u.pk, u2.pk)
        self.assertEqual(
            resolve_identity({**info, "groups": ["stash-owners"]}).pk, u.pk
        )
        with self.assertRaises(PermissionError):
            resolve_identity({**info, "groups": []})
        with self.assertRaises(ValueError):
            resolve_identity({**info, "iss": "https://evil.example.com"})
        for s in ["//evil.example.com", "/\\evil", "https://evil.example.com", "/\n"]:
            self.assertEqual(safe_next(s), "/")

    def test_local_login_deep_link_logout(self):
        c = Client(enforce_csrf_checks=True)
        r = c.get("/auth/login?next=/c/B014")
        csrf = c.cookies["csrftoken"].value
        r = c.post(
            "/auth/login",
            {
                "username": "owner",
                "password": "a very strong passphrase",
                "next": "/c/B014",
                "csrfmiddlewaretoken": csrf,
            },
        )
        self.assertEqual(r.url, "/c/B014")
        self.assertEqual(c.get("/api/me").status_code, 200)
        self.assertEqual(c.get("/auth/logout").status_code, 405)
        c.post("/auth/logout", HTTP_X_CSRFTOKEN=c.cookies["csrftoken"].value)
        self.assertEqual(c.get("/api/me").status_code, 401)

    def test_invalid_media_and_unknown_quantity(self):
        a = self.tub("C1")
        self.assertEqual(
            self.post(
                "items",
                {
                    "container_id": a["id"],
                    "photo": base64.b64encode(b'<svg onload="alert(1)">').decode(),
                },
            ).status_code,
            400,
        )
        self.assertEqual(
            self.post(
                "items", {"container_id": a["id"], "title": "count", "quantity": -1}
            ).status_code,
            400,
        )

    def test_draft_cannot_cross_account_after_session_changes(self):
        a = self.tub("A1")
        member = Client()
        member.force_login(self.member)
        r = member.post(
            "/api/items",
            json.dumps({"title": "old owner draft", "container_id": a["id"]}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            HTTP_X_STASH_USER=str(self.owner.pk),
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Item.objects.count(), 0)
