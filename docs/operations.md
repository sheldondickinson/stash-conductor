# Operations, export/import and recovery

The app stores SQLite and immutable original photos under `STASH_DATA` (`/data` in Docker). Schema changes use committed Django migrations, applied before Gunicorn starts. Retain a backup before upgrading. Pin the release commit/image and keep the previous image for rollback. Two workers share SQLite transactions with immediate write locking and a 20-second lock timeout.

## Backup

```sh
docker compose exec stash python scripts/backup.py /tmp/stash-backup.tar.gz
docker compose cp stash:/tmp/stash-backup.tar.gz ./stash-backup.tar.gz
```

Use a unique destination each time. The script uses SQLite's online backup API, copies immutable originals and thumbnails, checks referenced originals, and includes a SHA-256 manifest. Keep `.env`, deployment Compose/proxy configuration and the exact source/image release in a separate protected recovery bundle. These contain secrets; never commit them. Store backups on a separate protected disk/NAS; encrypt private archives. Schedule the command using your existing backup system. No retention deletion is performed by this project.

## Isolated restore / portable import

```sh
python scripts/restore.py stash-backup.tar.gz restored-data
# Destination must not exist. Hashes, SQLite integrity and photo references are checked.
STASH_DATA="$PWD/restored-data" python manage.py clearsessions
STASH_DATA="$PWD/restored-data" python manage.py migrate
# Use a private loopback origin and a fresh SECRET_KEY when rehearsing.
STASH_DATA="$PWD/restored-data" DEBUG=1 python manage.py runserver 127.0.0.1:8001
```

`clearsessions` removes expired sessions only. For a recovery into a different trust boundary, invalidate **all** sessions and integration/pairing credentials before making it accessible:

```sh
STASH_DATA="$PWD/restored-data" python manage.py shell -c 'from django.contrib.sessions.models import Session; from inventory.models import ApiToken, Pairing; Session.objects.all().delete(); ApiToken.objects.all().delete(); Pairing.objects.all().update(revoked=True)'
```

This bundle is the lossless export/import format, including identities, revisions and history. Settings also exports readable JSON for analysis and integration. JSON alone intentionally is not a full backup because it excludes photos and account/session configuration. There is no destructive merge-import into a running household.

Check an existing item, its movement history and its original photo in the isolated restored instance. Never point a rehearsal at the production directory. To replace a failed production installation, stop it, preserve its old directory, restore to a new directory, set ownership to container UID 10001, then update the volume mount. Reuse the same version first; migrate later. Test authentication and media access before exposing the restored service.

## Optional enrichment

Basic Stash makes no AI requests. A trusted operator may configure `AI_ENDPOINT` and `AI_TOKEN` privately and run `python manage.py enrich ITEM_UUID` in a separate process. This sends exactly one chosen original photo and phrase, with a 45-second timeout, no redirects and a 32 KB response limit. The endpoint must return JSON. It is a provider interface, not a bundled commercial-provider integration. There is no per-capture browsing, automatic identity merge, counting or movement. Unconfirmed results are visible in item details; copy only reviewed facts into confirmed fields. Record source and units.

## Boundaries

Foreground reconnect retries pending drafts; iOS background sync is not assumed. Cold offline launch cannot fetch private inventory. Photos support JPEG, PNG and WebP; configure iPhone export/capture for a supported format if a library original is HEIC. Image orientation is applied to thumbnails, originals are retained.

Search is a household-scale text/fuzzy scan, not a large-catalogue search engine. Inventory is one shared household. No live telemetry, purchasing, flashing or BOM management. Splits produce separate physical records and explicit history; split undo requires a manual count/location correction to avoid undoing later independent child changes.

## Moving release and portability

Version 0.2 adds additive migrations for independent tags, encoder reservations, locations, box packing metadata and print jobs. Existing container UUIDs, codes, `/c/` and `/i/` URLs remain unchanged. Each new `/t/` URL has a 128 bit random token and a database primary key constraint. All application accounts belong to the one configured household; this is not a multi tenant hosted service.

The SQLite backup already includes tag mappings, histories, reservations and printer preferences. Photos remain immutable in the same directory. Include the operator printer configuration, staged station firmware digest, deployment Compose, runtime settings, exact release/image and encryption recovery key in the protected recovery bundle. Station credentials are hashed on the server: restore preserves validation but cannot recover a lost device credential. Revoke and provision a replacement when necessary. Never put recovery material in the public source repository.

Before moving, export the readable moving manifest and batch results and keep an encrypted full backup on a device separate from the home servers. Test restore into an isolated directory. Preserve the public origin hostname and all existing database identifiers: tags do not need rewriting when only the home WAN address changes. Reestablish DNS, trusted HTTPS, reverse proxy/tunnel, backend storage and identity provider with its exact callback. Restore the original identity issuer and subject mappings. A new IdP issuer is a controlled identity migration, not an automatic email match.

A home server outage makes online inventory and household login unavailable. Local drafts and a previously exported manifest help, but they are not a redundant backend. The backend, Gatehouse, power, LAN, DNS and tunnel connector must remain available or be restored at the new site. No hosting migration, subscription or paid AI service is introduced. A supported standalone deployment can use `AUTH_MODE=local` and the existing interactive account management command; keep any emergency configuration change private and revert it deliberately after IdP recovery.

The web and printer worker share a data volume. Start the web service and finish migrations before starting `python manage.py print_worker`. Preserve the previous image and backup. For rollback, stop both processes and restore a matching database/image into a new directory; do not run the old model against a newly migrated database by assumption. During restore, `sending` print jobs become uncertain on worker startup; old queued jobs are held. Review them before resuming to prevent surprise labels after an outage.
