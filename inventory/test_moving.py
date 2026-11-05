import io
import json
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import Container, Item, Location, PrintJob, Station, Tag
from .moving import whereabouts
from .printing import png, work_once


class MovingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("packer", is_staff=True)
        self.client.force_login(self.user)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ov = override_settings(
            DATA_DIR=Path(self.tmp.name),
            MEDIA_ROOT=Path(self.tmp.name),
            ORIGIN="https://stash.example.com",
        )
        self.ov.enable()
        self.addCleanup(self.ov.disable)

    def post(self, url, data, key=None, client=None):
        return (client or self.client).post(
            "/api/" + url,
            json.dumps(data),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
        )

    def batch(self):
        return self.post("batches", {"name": "Test batch", "count": 3}).json()["tags"]

    def test_claim_revision_replacement_and_private_routes(self):
        a, b, c = self.batch()
        key = str(uuid.uuid4())
        p = {
            "revision": 1,
            "create_box": {"code": "BOX1", "description": "Winter clothes"},
        }
        first = self.post("tags/" + a["token"], p, key)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json(), self.post("tags/" + a["token"], p, key).json())
        self.assertEqual(Container.objects.count(), 1)
        member = User.objects.create_user("second")
        other = Client()
        other.force_login(member)
        self.assertEqual(
            self.post("tags/" + a["token"], p, client=other).status_code, 409
        )
        result = self.post(
            "tags/" + b["token"],
            {
                "action": "replace",
                "revision": 1,
                "replace_code": a["token"],
                "replace_revision": 2,
                "confirm": True,
            },
        )
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(Container.objects.count(), 1)
        old = Tag.objects.get(pk=a["token"])
        self.assertEqual(old.state, "retired")
        self.assertEqual(old.container_id, Tag.objects.get(pk=b["token"]).container_id)
        for path in [
            "tags",
            "batches",
            "printer",
            "print-jobs",
            "locations",
            "activity",
            "moving-manifest",
            "stations",
            "label-preview",
        ]:
            self.assertEqual(Client().get("/api/" + path).status_code, 401)
        self.assertEqual(
            self.post("tags/" + c["token"], p, client=Client()).status_code, 401
        )
        r = Client().get("/t/" + a["token"] + "?pack=1&room=study")
        self.assertEqual(r.status_code, 302)
        self.assertIn("%3Fpack%3D1%26room%3Dstudy", r.url)

    def test_hierarchical_locations_atomic_moves_and_search(self):
        site = Location.objects.create(code="SITE", name="New site")
        shelf = Location.objects.create(code="SHELF", name="Garage shelf", parent=site)
        box = Container.objects.create(
            code="B1", physical_location=shelf, destination="Study", keywords="fragile"
        )
        inner = Container.objects.create(code="B2", parent=box)
        Item.objects.create(title="Notebook", container=inner)
        self.assertEqual(whereabouts(inner), "New site / Garage shelf")
        self.assertEqual(
            self.post(
                "locations/" + str(site.id), {"revision": 1, "parent_id": str(shelf.id)}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.post(
                "containers/" + str(box.id), {"revision": 1, "parent_id": str(inner.id)}
            ).status_code,
            409,
        )
        dest = Location.objects.create(code="STORE", name="Temporary store")
        payload = {
            "location_id": str(dest.id),
            "location_revision": 1,
            "boxes": [
                {"id": str(box.id), "revision": 1},
                {"id": str(inner.id), "revision": 0},
            ],
        }
        self.assertEqual(self.post("moves", payload).status_code, 409)
        box.refresh_from_db()
        self.assertEqual(box.physical_location_id, shelf.id)
        payload["boxes"] = payload["boxes"][:1]
        self.assertEqual(self.post("moves", payload).status_code, 200)
        inner.refresh_from_db()
        self.assertEqual(whereabouts(inner), "Temporary store")
        self.assertEqual(
            len(self.client.get("/api/items?q=Temporary").json()["items"]), 1
        )
        manifest = self.client.get("/api/moving-manifest").json()
        self.assertEqual(len(manifest["boxes"]), 2)
        export = self.client.get("/api/export").json()
        self.assertIn("locations", export)
        self.assertIn("tags", export)
        tag = self.batch()[0]
        self.post(
            "tags/" + tag["token"], {"revision": 1, "container_id": str(inner.id)}
        )
        self.assertEqual(
            len(self.client.get("/api/items?q=" + tag["code"]).json()["items"]), 1
        )

    def test_station_recovery_and_readback_gate(self):
        tags = self.batch()
        out = self.post("stations", {"name": "Bench"}).json()
        s = out["station"]
        token = out["credential"]
        sid = s["id"]

        def exchange(p):
            return Client().post(
                "/api/station/" + sid + "/exchange",
                json.dumps(p),
                content_type="application/json",
                HTTP_AUTHORIZATION="Bearer " + token,
            )

        p = {
            "action": "reserve",
            "uid": "04112233445566",
            "blank": True,
            "kind": "NTAG213",
        }
        self.assertEqual(exchange(p).status_code, 409)
        self.post(
            "stations/" + sid,
            {
                "action": "arm",
                "revision": 1,
                "batch_id": tags[0]["batch_id"],
                "print_after": True,
            },
        )
        one = exchange(p)
        self.assertEqual(one.status_code, 200, one.content)
        v = one.json()
        self.assertEqual(exchange(p).json()["reservation_id"], v["reservation_id"])
        self.assertEqual(exchange({**p, "uid": "04112233445577"}).status_code, 409)
        verify = {
            "action": "verify",
            "uid": p["uid"],
            "reservation_id": v["reservation_id"],
            "readback": "https://wrong.example",
        }
        self.assertEqual(exchange(verify).status_code, 409)
        self.assertEqual(PrintJob.objects.count(), 0)
        verify["readback"] = v["tag"]["url"]
        a = exchange(verify)
        self.assertEqual(a.status_code, 200, a.content)
        self.assertEqual(exchange(verify).json(), a.json())
        self.assertEqual(PrintJob.objects.count(), 1)
        second = exchange({**p, "uid": "04112233445577"}).json()
        station = self.client.get("/api/stations").json()["stations"][0]
        self.assertTrue(station["reservations"])
        skipped = self.post(
            "stations/" + sid,
            {
                "action": "skip",
                "revision": station["revision"],
                "reservation_id": second["reservation_id"],
            },
        ).json()
        self.assertFalse(exchange({**p, "uid": "04112233445577"}).json()["may_write"])
        resumed = self.post(
            "stations/" + sid,
            {
                "action": "resume",
                "revision": skipped["revision"],
                "reservation_id": second["reservation_id"],
            },
        )
        self.assertEqual(resumed.status_code, 200)
        recovered = exchange({**p, "uid": "04112233445577"}).json()
        self.assertEqual(recovered["reservation_id"], second["reservation_id"])
        self.assertTrue(recovered["may_write"])
        self.assertEqual(
            Client()
            .get("/api/items", HTTP_AUTHORIZATION="Bearer " + token)
            .status_code,
            401,
        )
        self.assertFalse(exchange({"action": "boot"}).json()["armed"])
        self.assertFalse(exchange({**p, "uid": "04112233445577"}).json()["may_write"])
        Station.objects.filter(pk=sid).update(revoked=True)
        self.assertNotEqual(exchange(p).status_code, 200)

    def test_queue_duplicate_crash_offline_and_stale(self):
        key = str(uuid.uuid4())
        p = {"refs": ["test"], "copies": 1}
        a = self.post("print-jobs", p, key)
        self.assertEqual(a.status_code, 200, a.content)
        self.assertEqual(self.post("print-jobs", p, key).json(), a.json())
        self.assertEqual(PrintJob.objects.count(), 1)
        with patch(
            "inventory.printing.bridge",
            return_value={"state": "outcome_unknown", "detail": "Timed out"},
        ) as b:
            self.assertTrue(work_once())
            self.assertFalse(work_once())
            self.assertEqual(b.call_count, 1)
        j = PrintJob.objects.get()
        self.assertEqual(j.state, "outcome_unknown")
        self.assertEqual(
            self.post("print-jobs/" + str(j.id), {"action": "cancel"}).status_code, 409
        )
        self.post("print-jobs", p)
        PrintJob.objects.filter(state="queued").update(
            created=timezone.now() - timedelta(hours=2)
        )
        work_once()
        self.assertEqual(PrintJob.objects.filter(state="held").count(), 1)
        PrintJob.objects.filter(state="held").update(state="sending")
        work_once()
        self.assertEqual(PrintJob.objects.filter(state="outcome_unknown").count(), 2)

    def test_qr_actual_raster_decodes_and_matches(self):
        import zxingcpp
        from PIL import Image

        for tape in [18, 24]:
            url = "https://stash.example.com/t/" + ("x" * 22)
            raw = png(
                {"code": "T1234ABCD", "title": "Winter blankets", "url": url}, tape
            )
            im = Image.open(io.BytesIO(raw))
            self.assertEqual(im.height, 112 if tape == 18 else 128)
            decoded = zxingcpp.read_barcodes(im.convert("RGB"))
            self.assertEqual([d.text for d in decoded], [url])

    def test_normal_queue_processes_without_reprint_and_saves_device_status(self):
        from .models import Printer

        out = self.post("print-jobs", {"refs": ["test"], "copies": 1}).json()
        observed = {"Status": {"MediaWidthMM": 24, "Type": "error", "ErrorInfo2": 4}}
        with patch(
            "inventory.printing.bridge",
            return_value={
                "state": "failed",
                "detail": "No print data sent. Unrecognised error 00/04.",
                "status": observed,
                "status_detail": "Unrecognised printer error 00/04.",
            },
        ) as bridge_mock:
            self.assertTrue(work_once())
            self.assertFalse(work_once())
            self.assertEqual(bridge_mock.call_count, 1)
        self.assertEqual(PrintJob.objects.get(pk=out["id"]).state, "failed")
        p = Printer.objects.get(pk=1)
        self.assertEqual(p.status["status"], observed)
        self.assertIsNotNone(p.last_check)
        self.assertEqual(PrintJob.objects.count(), 1)

    def test_member_can_pack_but_not_provision_printer_or_station(self):
        c = Client()
        c.force_login(User.objects.create_user("member"))
        self.assertEqual(
            self.post("batches", {"name": "Shared", "count": 1}, client=c).status_code,
            200,
        )
        self.assertEqual(self.post("stations", {}, client=c).status_code, 403)
        self.assertEqual(
            self.post(
                "printer",
                {"revision": 1, "tape_mm": 24, "finishing": "single-full"},
                client=c,
            ).status_code,
            403,
        )

    def test_login_destinations_are_scoped_to_each_oidc_state(self):
        from types import SimpleNamespace
        from unittest.mock import Mock

        from django.http import HttpResponseRedirect

        from . import auth

        identity = Mock()
        identity.authorize_redirect.side_effect = [
            HttpResponseRedirect("https://identity.example/authorize?state=first"),
            HttpResponseRedirect("https://identity.example/authorize?state=second"),
        ]
        identity.authorize_access_token.return_value = {"userinfo": {"sub": "test"}}
        anonymous = Client()
        with (
            override_settings(AUTH_MODE="oidc"),
            patch.object(auth, "oauth", SimpleNamespace(identity=identity)),
            patch.object(auth, "resolve_identity", return_value=self.user),
        ):
            a = anonymous.get("/auth/login", {"next": "/t/abc?pack=1&room=study"})
            b = anonymous.get("/auth/login", {"next": "/c/B1?view=photos"})
            self.assertEqual(a.status_code, 302)
            self.assertEqual(b.status_code, 302)
            self.assertEqual(
                anonymous.get("/auth/callback?state=first").url,
                "/t/abc?pack=1&room=study",
            )
            self.assertEqual(
                anonymous.get("/auth/callback?state=second").url, "/c/B1?view=photos"
            )
        for bad in [
            "https://evil.example",
            "//evil.example",
            "/%2fevil.example",
            "/%5cevil",
            "/%0d%0aLocation:evil",
        ]:
            self.assertEqual(auth.safe_next(bad), "/")
