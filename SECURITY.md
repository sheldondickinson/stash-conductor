# Security

Inventory, originals, exports, history and all API routes require authentication. Owners manage user access and export; members have full everyday inventory permissions. Stash is one household per installation, not a hosted multi-tenant service.

Report vulnerabilities privately to the repository maintainer; do not attach real records, photos, credentials or session cookies to public issues.

Deploy behind a trusted TLS proxy; backend ports must remain unpublished or loopback-only. Enforce a 32 MB body limit and an internet-facing rate limit at the proxy. Images are decoded and bounded by size and pixel count; SVG and executable uploads are rejected. Original EXIF metadata is retained with originals; it is not included in thumbnails. Originals remain authenticated.

Sessions and CSRF use Django; OIDC uses Authlib. Writes require idempotency keys, authenticated attribution and revision checks. Client-supplied identity headers are ignored. Browser HTML renders user strings with escaping. CSP restricts scripts, frames and connections to this origin; no analytics or remote font scripts are included.

Unsent drafts and saved draft thumbnails are local private browser data. They are namespaced by account and never replayed under another user, but are not encrypted against someone with access to the unlocked browser profile. Use trusted devices. Application removal is undoable, not secure erasure. Backups contain private data and sessions; protect and encrypt them using your backup system, and clear sessions after a restore.

AI is disabled by default. Enabling the explicitly selected enrichment command transmits that original photo and description to your configured endpoint. Suggestions remain unconfirmed and must never be used as electrical safety advice. Do not put device passwords in notes.
