# Authenticated API v1

Same origin `/api`. Responses are JSON except media/QR PNG. No anonymous inventory API exists. All users in one installation share one household. Owner-only routes are explicitly marked below.

Authenticate with the secure browser session and `X-CSRFToken` returned by `GET /api/me`, or an owner-issued `Authorization: Bearer TOKEN` credential. Tokens expire after 30 days and have read or read/write permission. Never put credentials in URLs. Keep automation tokens server-side. Stash does not accept caller-supplied identity headers.

Every POST uses `Content-Type: application/json` and an `Idempotency-Key` of 16–100 letters, numbers, `_` or `-` (UUIDs work). Reuse the same key and identical body when a response is lost. It returns the original receipt. Reusing a key with a different path/body returns 409. Existing-record mutations require the current `revision`; stale edits return 409. Multi-item writes are atomic. Errors contain `error` and a relevant 400/401/403/404/405/409 status.

| Method/path | Purpose |
|---|---|
| GET `/api/me` | User, role, namespace and CSRF token |
| GET/POST `/api/containers` | List / create; `code`, optional `name`, `location`, `count` (batch 1–50), photo |
| GET/POST `/api/containers/{uuid}` | Read / change name, photo or physical location with revision |
| GET `/api/items?q=...&container=UUID` | Search descriptions, original words, aliases and confirmed metadata |
| POST `/api/items` | Capture: `container_id`, `title` or `photo`, optional `quantity` and `unit` |
| GET `/api/items/{uuid}` | Record and actor-attributed before/after history |
| POST `/api/items/{uuid}` | `revision`, `action` and relevant fields |
| POST `/api/bulk` | `action`, `items:[{id,revision}]`, optional destination fields; all-or-nothing |
| POST `/api/undo/{event_uuid}` | Revision-checked reversal; retains history |
| GET `/api/media/{name}` | Authenticated original or thumbnail |
| GET `/api/label/{code}` | Real PNG QR encoding the canonical container URL |
| GET `/api/export` | Owner: readable inventory/history JSON; not a full photo backup |
| GET/POST `/api/users` | Owner: local enrolment/disable; OIDC enrolment stays at IdP |
| GET/POST `/api/tokens` | Owner: list/create/revoke 30-day API credentials |
| GET/POST `/api/pairings` | Current user: pair/revoke an installation |
| POST `/api/consume` | Consume the current user's pending destination for an installation |

Item actions: `edit`, `take`, `return`, `move`, `missing`, `unknown`, `used`, `remove`, `split`. `return` defaults to the previous tub; supply `container_id` to choose another. `take` optionally accepts `destination` (person/project/workbench). `split` requires a known `quantity` less than the current count and a destination tub. Serialised devices cannot be split. Unknown counts remain JSON `null`.

Photo fields contain base64 image bytes or a data URL, maximum 20 MB decoded / 40 megapixels. Accepted formats: JPEG, PNG, WebP. Capture stores the original and a JPEG thumbnail. Send the identical body and request key after network failure; photos are content-addressed and captures are not duplicated. The reverse proxy must cap the whole request at 32 MB.

Metadata is a JSON object. Suggested keys: manufacturer, model, input_voltage, logic_voltage, interfaces, ratings, pinout, datasheet, source, serial, mac, firmware, test_status, test_notes, test_date, installed_location, project, device_link. Include units and provenance. `original` is preserved independently of later name edits. AI suggestions are separate unconfirmed objects and are excluded from confirmed-metadata search.

## Navigation-only Shortcut API

`POST /api/pairings` with `{installation: "random-browser-installation-id", label: "My phone"}` returns a credential once in the response and a dedicated endpoint. Store it in the private Shortcut. `POST /api/handoff/{pairing_uuid}` with that credential in an Authorization Bearer header and `{"code":"B014"}` sets a 60-second destination. This endpoint has no inventory read/write authority. The PWA POSTs `{installation: ...}` to `/api/consume` with its normal authenticated session. Destinations are scoped to both user and installation, consumed once, and newest scan wins. Pair from inside the installed PWA, not a separate Safari profile. Revoke with `{revoke: "pairing_uuid"}`.

Stable human links are `/c/CODE` and `/i/UUID`; login preserves safe same-origin destinations. Future Conductor tools can call these APIs directly without maintaining a mirror.


## Moving, tags and labels

The same household authentication, CSRF, per user idempotency receipts and revision checks cover these additions:

| Method and path | Purpose |
| --- | --- |
| GET/POST `/api/locations` and `/api/locations/{uuid}` | Hierarchical physical locations; cycles rejected |
| POST `/api/moves` | Atomic `location_id`, `location_revision`, `boxes:[{id,revision}]`, optional `packing_state` |
| GET `/api/activity` | Actor attributed recent changes; optional `entity_id` |
| GET/POST `/api/batches` | List or generate 1 to 200 independent tags |
| GET `/api/tags` | Optional `batch` or `box` filter |
| GET/POST `/api/tags/{token_or_code}` | Assign, reassign, replace, lost, retire, reactivate, phone prepare/readback |
| GET/POST `/api/stations` and `/api/stations/{uuid}` | Owner creates/revokes narrow identities; members explicitly arm/disarm |
| GET/POST `/api/printer` | Read and check; owner saves tape and cutter preferences |
| GET/POST `/api/print-jobs` and `/api/print-jobs/{uuid}` | Structured queue, safe cancellation, held resume, deliberate reprint |
| GET `/api/label-preview?ref=box:UUID` | Same raster as printing; `tag:TOKEN` or `test` also accepted; PNG or `format=svg` |
| GET `/api/moving-manifest` | JSON or `format=csv`; readable fallback inventory |

Box payloads additionally accept `physical_location_id`, `parent_id`, `destination`, `description`, `packing_state`, `fragile`, `heavy`, `priority`, `category`, `keywords`, `storage_notes` and `review_date`. Physical location and parent containment are distinct from the destination room. Revision conflicts never silently overwrite another person's changes.

Station credentials are separate from household API tokens. POST `/api/station/{uuid}/exchange` accepts only boot disarming, health, inspect, reserve and exact readback verification under its revocable Bearer credential. Allocation requires a deliberately armed batch. Reserved URLs and UIDs survive retries and are never recycled. GET `/api/station/{uuid}/firmware` exposes only the operator staged binary to that station identity. Neither endpoint grants inventory reads or arbitrary job instructions. See the [station protocol and commissioning guide](tag-station.md).

## Paper box batches

`GET /api/box-preview?count=12` returns unreserved names, codes and page count. `POST /api/box-batches` accepts `request_id` (UUID), `count` (1 to 240), optional `name`, `physical_location_id`, `destination`, `proposed_names` and `name_overrides` keyed by zero based position. Use the same UUID as Idempotency-Key and retain the identical payload for retry. The response contains committed boxes and batch ID. Codes are allocated by the server.

`GET /api/box-batches?q=...` lists up to 100 matching batches; `GET /api/box-batches/<uuid>` returns saved membership and current names. `GET /api/box-batches/<uuid>/labels.pdf` downloads pairs without creating records. `GET /api/box-labels.pdf?codes=B001,B002` prints selected existing boxes only, maximum 240. PDF failures return 503 with retry guidance and leave creation committed. All endpoints use existing household authentication.

`POST /api/name-unnamed-boxes` accepts `boxes: [{id, revision}]` and names only currently unnamed selections atomically. Ordinary `POST /api/containers` and tag `create_box` share the server name and code allocator when fields are blank. Explicit names and valid unused manual codes remain supported. Inventory JSON version 3 adds box batches, membership and allocation metadata. Backups include these database tables automatically.
