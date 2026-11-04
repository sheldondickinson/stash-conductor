# iPhone, QR, NFC and Home Screen

Open the configured HTTPS origin in Safari, sign in and use Share → Add to Home Screen. The existing manifest, touch icons and layout remain. Camera scanning and ordinary keyboard dictation work through standard phone controls. Test actual camera, dictation and cold/warm launch on the target iPhone.

Use the independent tag registry and [phone preparation workflow](packing.md) for new NFC stickers. Each tag gets its own permanent `/t/TOKEN` HTTPS NDEF URI; its matching QR and readable code point to that same registry entry. Existing `/c/CODE` and `/i/UUID` links remain supported. Never store a login or pairing credential on a tag.

Apple documents background NDEF URI reading on supported iPhones. After the notification tap, a URL can open a linked native application or Safari. This does not guarantee launch into an installed PWA. The dependable path is the HTTPS browser route, with authentication returning to the exact tag, box or item and its query parameters. Stash does not depend on Web NFC, a custom URL scheme, a personal automation for each box or Home Assistant.

## Physical acceptance

On each household phone, record its model and iOS version. Sign out, scan a prepared tag, sign in and confirm the intended box opens. Repeat while signed in, from mobile data, and with the installed Home Screen app both cold and already running. Check a second tag to catch stale destinations. Test the final QR and NFC mounting position and note required notification taps. These are physical acceptance checks, not outcomes established by desktop browser tests.

## Existing optional Shortcut compatibility

The original OpenTub pairing and short lived handoff API is retained for existing users. It can pass a box code to one authenticated installation, with a 60 second expiry and revocation in Settings. It carries no inventory authority. See [the API contract](api.md). No new Shortcut is required for packing or batch tag preparation.

Earlier workaround experiments used unofficial launch schemes. They are not part of the supported preparation workflow and no PWA launch claim relies on them. Use the normal HTTPS URL when a phone does not retain an installed app destination.

Sources: [Apple background NFC](https://developer.apple.com/documentation/corenfc/adding-support-for-background-tag-reading), [Apple Shortcut input URL](https://support.apple.com/en-au/guide/shortcuts/apd624386f42/ios).
