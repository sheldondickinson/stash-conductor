# Verification record

Release candidate 0.1.0, 9 October 2026.

Verified with synthetic data in isolated development/test storage:

- Photo-only unknown → enrichment edit → search → take out → return to another tub → move tub → missing → correct; identity and history preserved.
- Shared inventory for owner/member; owner-only user/export routes denied to members. Counted splits preserve total; unknown counts cannot split; serialised installed device remains in use.
- Duplicate requests return the same receipt, altered replays and stale revisions return 409; an invalid member of a bulk move rolls back the whole operation.
- Anonymous API/media/export denial, CSRF rejection, read-only token write denial, safe deep-link login and local logout.
- OIDC identity binding by issuer/subject, group allow/deny; same email never links separate subjects. Production callback/role verification is deployment-specific and kept outside this public repository.
- Pairing scoped by user and installation, expiry, single consumption, wrong-installation isolation and revocation.
- Real desktop Chromium browser: text capture, file upload/photo-only record, network-offline draft then foreground retry, no duplicate record, 390 px responsive layout without horizontal overflow.
- Generated container QR decoded back to the exact application URL with bundled jsQR.
- SQLite/photo backup restored into a new isolated directory; three synthetic records and one original photo recovered and hash-verified.
- Django checks/migrations and dependency vulnerability audit passed for the pinned environment.

Physical iPhone installation, camera hardware, native keyboard dictation, background NFC, dynamic Shortcut input and cold/warm installed-PWA path retention remain manual acceptance checks in [iphone.md](iphone.md). Desktop tests do not establish those outcomes. Human five/ten-second capture targets have not been measured. Optional external AI-provider execution is not enabled or claimed.

The portable Docker installation and CI build are tested without household configuration. Public examples contain only synthetic data and example.com hosts. No synthetic inventory is seeded by the application.

## Moving release verification, 4 November 2026

The expanded Django suite passes 16 tests covering existing item/photo/history behaviour plus tag claims, replacement, authorisation, revision conflicts, nested locations, atomic moves, readback gating, station revocation, print idempotency and conservative worker recovery. A separate simultaneous HTTP test against a real SQLite development server accepted exactly one of two tag claims (200 and 409) and returned the same print job for concurrent duplicate submissions. Mocked OIDC callbacks preserve two independent state-specific destinations including query strings; this does not represent a human IdP login.

A real headless Chrome session at a 390 by 844 viewport created a prepared-tag box with a photo, lost connectivity during editing, retained text/photo in IndexedDB, recovered after reload and saved on reconnection. PNG labels at both supported widths decode to the exact expected URL using an independent ZXing decoder. The Go bridge builds; the pinned upstream protocol tests pass. PlatformIO compiles the ESP32 reference firmware, and native NDEF codec checks pass. A complete synthetic database/photo archive restores into an isolated directory with photo hashes and tag assignments intact.

These are software and browser checks. They do not establish physical print completion, QR readability on the target iPhone, NFC writing on the actual XC4506, physical OTA recovery, installed iOS PWA launch, mobile data connectivity or separate human logins. Commission those against the deployed environment using the printing, station and iPhone guides. No hardware has been flashed merely to satisfy a build check.

## Paper batch addition

Twenty three automated tests pass, including the existing suite and seven focused paper/naming tests. An isolated disk database preserved duplicate legacy names and B042 on migration, then real simultaneous HTTP requests allocated 24 distinct names/codes and duplicate submissions returned a single batch. Quantities 1, 11, 12, 13 and 24 generated the expected pages and 122 total QR labels; each 300 dpi rendered label decoded independently to its saved box URL. Full and partial pages were visually inspected. Maximum 240 boxes and 20 PDF pages completed in under two seconds in the local fixture.

Chromium verified response loss after server commit, reload/resume and PDF download failure/retry without extra boxes. The form and saved batch view fit 320, 390, 834 and 1440 widths; enlarged text and reduced motion were checked. All sample boxes and PDFs used disposable local records. The physical paper print, iPhone scan and mobile data check are separate. No new production example boxes are part of deployment.
