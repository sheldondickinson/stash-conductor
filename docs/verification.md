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
