# Packing and storage

Open **Pack** to prepare tags, work through boxes, move them and print a manifest. Existing Find, Add, Containers and item retrieval/return history remain available.

1. Create a batch in **Prepare tags**. Each tag has a different permanent URL and readable code. Generation is not encoding.
2. Encode and read back one sticker, using the station or the phone workflow below. Optionally queue its matching label after verification. Check the print queue separately.
3. Open the tag URL or scan its QR. Create a box or select an existing box. Assignment requires a confirmed server response.
4. Add a whole box description, photo, physical location and intended room. Category, count and review date are optional. Your keyboard microphone can dictate into ordinary text fields.
5. Save, then choose **Add items and photos**, **Print label** or **Scan next box**. Detailed items are optional. The Add screen supports repeated photo captures and quantities.

Use the permanent identifier label without a title when contents will change. A second label with the short title can be replaced separately. Never create another inventory box just to reprint or replace a tag.

## Places and moves

Create locations from broad to specific: property, garage, shelf, position. A storage unit or temporary site is another top level location. Boxes may also contain other boxes. Cycles are rejected. Current physical whereabouts are separate from the intended destination room.

Scan a location tag, scan several assigned box tags or QR labels, then confirm the move. Duplicate scans are rejected. A changed box or destination revision stops the whole move; refresh and review before trying again. There is no partial silent move. Parent movement changes effective child locations without editing every item.

Filter Pack for boxes still being packed, in transit, stored, unpacked, or priority essentials. Search includes box fields and item words. Recent changes records the actor and time. Item **Take out** and **Return** retain their own history. Storage notes and review dates have no automatic notification schedule.

## Local drafts and connection loss

Open forms save text and photos into this account's IndexedDB namespace. A retained draft is explicitly different from a server save. Keep the page open when packing offline. Existing item captures use operation IDs and foreground retry; box edits, tag claims and location moves need an explicit online save. Cold offline launch shows a connection page, not a cached inventory. This release does not implement full offline synchronisation of shared data.

A box save keeps its operation ID and exact submitted payload for retry if the response is lost. Revision conflicts show the current server record and require a deliberate choice. On explicit logout, local account drafts and photos are cleared after warning about unsaved work. Service worker caches contain only public application assets; API results, inventory HTML, photos and authentication are never cached there. A shared browser profile is not a substitute for separate OS accounts on an untrusted shared computer.

## Phone tag fallback

NFC Tools for iOS supports writing URL records and reading NDEF data. In Stash choose **Copy next tag URL**. In NFC Tools use **Write → Add a record → URL**, paste the complete URL, then write one NTAG sticker. Use its **Read** view to read back that physical sticker. Paste the read URL into Stash and explicitly confirm that it came from the sticker. Only then does Stash record `phone_verified`. This is an operator attestation, unlike the station's automatic byte readback. Exporting URLs never marks them encoded.

Skip preserves the pending identity for later resumption. Export the batch JSON to keep codes, URLs, assignment and actual preparation results. No CSV import or automatic batch encoding capability is assumed for the phone app. Do not copy one URL onto multiple stickers intended as separate registry tags.

On supported iPhones, a background NDEF HTTPS read displays a notification. Tapping it opens the associated app or Safari. An installed PWA launch is not guaranteed. The dependable route is HTTPS, login, then the original tag or box path. No `webapp://` URL or per box Shortcut is required. Real cold/warm iPhone and mobile data checks remain commissioning tests.

Sources: [NFC Tools for iOS](https://www.wakdev.com/en/apps/nfc-tools-ios.html), [Apple background NFC](https://developer.apple.com/documentation/CoreNFC/adding-support-for-background-tag-reading).

Prepare twelve empty named boxes at once with **Create boxes in bulk**, then cut out paired A4 labels. See [paper label guide](paper-labels.md).
