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
