import io
import json
import uuid
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from pypdf import PdfReader

from .box_names import NAMES, normalise
from .models import BoxBatch, BoxBatchMember, BoxCode, Container, Location
from .paper_labels import box_label, qr_matrix
from .printing import definition, png


class BoxBatchTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("paper-owner", is_staff=True)
        self.member = User.objects.create_user("paper-member")
        self.client.force_login(self.owner)

    def post(self, path, data, key=None, client=None):
        return (client or self.client).post(
            "/api/" + path,
            json.dumps(data),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()),
        )

    def batch(self, count=12, **kw):
        payload = {"request_id": str(uuid.uuid4()), "count": count, **kw}
        response = self.post("box-batches", payload, payload["request_id"])
        self.assertEqual(response.status_code, 200, response.content)
        return payload, response.json()

    def test_quantities_saved_names_pairing_pages_and_reprints(self):
        for count in [1, 11, 12, 13, 24]:
            before = Container.objects.count()
            payload, batch = self.batch(count)
            self.assertEqual(Container.objects.count() - before, count)
            self.assertEqual(batch["count"], count)
            self.assertEqual(len({normalise(b["name"]) for b in batch["boxes"]}), count)
            self.assertTrue(
                all(b["name"] and b["packing_state"] == "empty" for b in batch["boxes"])
            )
            response = self.client.get(f"/api/box-batches/{batch['id']}/labels.pdf")
            self.assertEqual(response.status_code, 200)
            pdf = PdfReader(io.BytesIO(response.content))
            self.assertEqual(len(pdf.pages), (count + 11) // 12)
            for page_index, page in enumerate(pdf.pages):
                self.assertAlmostEqual(
                    float(page.mediabox.width) * 25.4 / 72, 210, places=3
                )
                self.assertAlmostEqual(
                    float(page.mediabox.height) * 25.4 / 72, 297, places=3
                )
                lines = [line.strip() for line in page.extract_text().splitlines()]
                expected = batch["boxes"][page_index * 12 : (page_index + 1) * 12]
                self.assertEqual(
                    [x for x in lines if x.startswith("B") and x[1:].isdigit()],
                    [b["code"] for b in expected for _ in range(2)],
                )
                for box in expected:
                    self.assertEqual(lines.count(box["name"]), 2)
            repeat = self.post("box-batches", payload, payload["request_id"])
            self.assertEqual(repeat.json(), batch)
            # A new receipt key with the same persisted request ID is still the same batch.
            self.assertEqual(self.post("box-batches", payload).json(), batch)
            self.client.get(f"/api/box-batches/{batch['id']}/labels.pdf")
            self.assertEqual(Container.objects.count(), before + count)

    def test_invalid_quantities_and_client_numbers_do_not_create(self):
        for count in [0, -1, 241, 1.5, "12", True, None]:
            r = self.post(
                "box-batches", {"request_id": str(uuid.uuid4()), "count": count}
            )
            self.assertEqual(r.status_code, 400)
        r = self.post("box-batches", {"request_id": str(uuid.uuid4()), "code": "B001"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Container.objects.count(), 0)
        self.assertEqual(BoxBatch.objects.count(), 0)

    def test_allocator_uses_next_number_and_does_not_reuse_reserved_codes(self):
        self.post("containers", {"code": "B042", "name": "Existing"})
        _, batch = self.batch(2)
        self.assertEqual([b["code"] for b in batch["boxes"]], ["B043", "B044"])
        self.assertEqual(self.post("containers", {"code": "B042"}).status_code, 409)
        self.assertEqual(self.post("containers", {"code": "B041"}).status_code, 200)
        self.assertEqual(
            self.post("containers", {}).json()["created"][0]["record"]["code"], "B045"
        )
        self.assertTrue(BoxCode.objects.filter(code="B045").exists())

    def test_single_scanned_explicit_and_unnamed_names(self):
        unnamed = self.post("containers", {}).json()["created"][0]["record"]
        self.assertIn(unnamed["name"], NAMES)
        explicit = self.post("containers", {"name": "  Family photographs  "}).json()[
            "created"
        ][0]["record"]
        self.assertEqual(explicit["name"], "Family photographs")
        tag = self.post("batches", {"count": 1, "name": "Test tags"}).json()["tags"][0]
        assigned = self.post(
            "tags/" + tag["token"],
            {
                "action": "assign",
                "revision": tag["revision"],
                "create_box": {"description": ""},
            },
        )
        self.assertEqual(assigned.status_code, 200, assigned.content)
        scanned = Container.objects.get(pk=assigned.json()["tag"]["container_id"])
        self.assertIn(scanned.name, NAMES)
        self.assertNotEqual(scanned.code, tag["code"])
        existing = Container.objects.create(code="OLD", name="")
        named = self.post(
            "name-unnamed-boxes", {"boxes": [{"id": str(existing.id), "revision": 1}]}
        )
        self.assertEqual(named.status_code, 200)
        existing.refresh_from_db()
        self.assertIn(existing.name, NAMES)
        self.assertEqual(
            self.post(
                "name-unnamed-boxes",
                {"boxes": [{"id": str(existing.id), "revision": 2}]},
            ).status_code,
            409,
        )

    def test_case_insensitive_names_exhaustion_and_stale_preview(self):
        Container.objects.create(code="LEGACY1", name=" nIgEl ")
        Container.objects.create(code="LEGACY2", name=" nIgEl ")
        with patch("inventory.box_names.NAMES", ("Nigel", "Mabel")):
            _, first = self.batch(3, proposed_names=["Nigel", "Mabel", "Nigel"])
            names = [b["name"] for b in first["boxes"]]
            self.assertNotIn("nigel", [normalise(n) for n in names])
            self.assertIn("Mabel", names)
            self.assertTrue(any(n.endswith(" 2") for n in names))
            self.assertEqual(len(set(names)), 3)
        self.assertEqual(Container.objects.get(code="LEGACY1").name, " nIgEl ")
        self.assertGreater(len(NAMES), 300)
        self.assertEqual(len(NAMES), len(set(NAMES)))

    def test_failure_after_commit_and_current_name_reprint(self):
        _, batch = self.batch(1)
        box = Container.objects.get(pk=batch["boxes"][0]["id"])
        url = box_label(box)["url"]
        with patch(
            "inventory.box_batches.render_pdf",
            side_effect=RuntimeError("simulated renderer outage"),
        ):
            r = self.client.get(f"/api/box-batches/{batch['id']}/labels.pdf")
            self.assertEqual(r.status_code, 503)
        self.assertEqual(Container.objects.count(), 1)
        box.name = "Florence"
        box.description = "Winter bedding"
        box.save()
        response = self.client.get(f"/api/box-batches/{batch['id']}/labels.pdf")
        self.assertEqual(
            PdfReader(io.BytesIO(response.content))
            .pages[0]
            .extract_text()
            .splitlines()
            .count("Florence"),
            2,
        )
        self.assertEqual(box_label(box)["url"], url)
        self.assertEqual(BoxBatchMember.objects.filter(batch_id=batch["id"]).count(), 1)
        self.assertEqual(definition("box:" + str(box.id))["title"], "Florence")
        self.assertEqual(
            self.client.get("/api/box-labels.pdf?codes=" + box.code).status_code, 200
        )
        self.assertEqual(Container.objects.count(), 1)
        # Both narrow layouts still decode the exact stable payload with required names.
        import zxingcpp
        from PIL import Image

        for tape in [18, 24]:
            results = zxingcpp.read_barcodes(
                Image.open(io.BytesIO(png(definition("box:" + str(box.id)), tape)))
            )
            self.assertEqual([r.text for r in results], [url])
        matrix = qr_matrix(url)
        self.assertTrue(all(not any(row) for row in matrix[:4] + matrix[-4:]))

    def test_permissions_shared_defaults_and_private_pdf(self):
        place = Location.objects.create(code="TEST", name="Temporary site")
        member = Client()
        member.force_login(self.member)
        payload = {
            "request_id": str(uuid.uuid4()),
            "count": 1,
            "physical_location_id": str(place.id),
            "destination": "Kitchen",
        }
        batch = self.post("box-batches", payload, client=member).json()
        box = batch["boxes"][0]
        self.assertEqual(box["physical_location_id"], str(place.id))
        self.assertEqual(box["destination"], "Kitchen")
        path = f"/api/box-batches/{batch['id']}/labels.pdf"
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertIn("no-store", member.get(path)["Cache-Control"])
        anonymous = Client()
        for endpoint in [
            "/api/box-preview",
            "/api/box-batches",
            path,
            "/api/box-labels.pdf?codes=" + box["code"],
        ]:
            self.assertEqual(anonymous.get(endpoint).status_code, 401)
        self.assertEqual(
            self.post("box-batches", payload, client=anonymous).status_code, 401
        )
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.member)
        self.assertEqual(
            self.post("box-batches", payload, client=csrf).status_code, 403
        )
        scan = anonymous.get("/c/" + box["code"] + "?pack=1&room=kitchen")
        self.assertEqual(scan.status_code, 302)
        self.assertIn(
            "next=%2Fc%2F" + box["code"] + "%3Fpack%3D1%26room%3Dkitchen",
            scan["Location"],
        )
