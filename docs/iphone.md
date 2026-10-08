# iPhone, QR, NFC and OpenTub

## Always-available route

Open `https://stash.example.com` in Safari. Sign in, Share → Add to Home Screen, enable Open as Web App if shown, then open **Stash**. The manifest, touch icon, maskable icon and safe-area layout are included. Scan QR from inside the app, choose a tub, or enter its printed code manually. Allow camera permission when requested. The text field supports the native keyboard microphone; there is no custom microphone service.

Every generated QR uses the real HTTPS `/c/B014` URL. The label can also be written as a normal HTTPS NDEF URI on an NFC tag. HTTPS may open Safari; that does not prove a PWA launch.

## Local Shortcut prototype: OpenTub

Create an Apple Shortcut named exactly **OpenTub**:

1. Receive text from Shortcut Input. If empty, Ask for Input (text).
2. Trim whitespace and change to uppercase.
3. Match Text against `^[A-Z0-9][A-Z0-9_-]{0,23}$`. If no match, Show Alert and Stop This Shortcut.
4. URL Encode the validated value.
5. Construct `webapp://stash.example.com/c/` followed by the encoded value, then Open URLs.

This `webapp://` step is a **workaround candidate, not an Apple API guarantee**. Test it on the actual installed app. If necessary separately test the full-HTTPS candidate `webapp://https://stash.example.com/c/B014`. Never use `webapp://://...`. Record which form, OS version and taps worked; do not assume the path survives.

A candidate NDEF URI for a tag is:

```
shortcuts://run-shortcut?name=OpenTub&input=text&text=B014
```

Use a second tag with B015. The tag contains only a code, never a pairing secret. Apple's Shortcut URL documentation defines input, but background NFC documentation excludes custom URI schemes. NFC Forum material reports observed support that may vary by device/OS. A desktop request cannot settle that difference.

## If the PWA opens but drops the path

Inside the **installed PWA**, Settings → Pair OpenTub Shortcut. Keep the resulting credential privately in that Shortcut. Add a Get Contents of URL step before opening the PWA root:

- URL: the pairing endpoint displayed by Stash.
- Method: POST; JSON body `code` = validated tub input.
- Header: Authorization = `Bearer` plus the displayed credential.
- Require successful response; then open the PWA root using the tested launch method.

On launch/foreground the authenticated PWA consumes that installation's destination once. It expires after 60 seconds; latest scan wins. Another user/installation cannot consume it. An unsaved capture remains attached to its original tub. Revoke old pairings in Settings. If a network request fails, show the error and retain the normal HTTPS/QR/manual path.

If direct background NFC cannot run the Shortcut, write an HTTPS tag or create a per-tag personal NFC automation in Shortcuts that passes that tag's code into OpenTub. Document required notification/confirmation taps; no silent/no-tap promise is made. Home Assistant is not required.

## Two-tag physical acceptance checklist — pending until performed

| Check | B014 | B015 |
|---|---|---|
| Phone model / iOS version / installed PWA recorded | ☐ | ☐ |
| Background scan actually launches Shortcut; note taps | ☐ | ☐ |
| Shortcut receives the correct dynamic code | ☐ | ☐ |
| Cold PWA opens at correct tub | ☐ | ☐ |
| Already-running PWA opens at correct tub | ☐ | ☐ |
| Alternate tags repeatedly; newest valid destination wins | ☐ | ☐ |
| Wait over 60 seconds; stale handoff ignored | ☐ | ☐ |
| Another person's paired phone unaffected | ☐ | ☐ |
| Unsaved photo remains with original tub | ☐ | ☐ |
| Camera upload, native dictation, QR and manual entry | ☐ | ☐ |

No fabricated `.shortcut` download is supplied. These instructions create a real local Shortcut using Apple's editor; a valid signed/shareable file must be exported from Apple tooling.

Sources: [Apple Shortcut input URL](https://support.apple.com/en-au/guide/shortcuts/apd624386f42/ios), [Apple background NFC](https://developer.apple.com/documentation/corenfc/adding-support-for-background-tag-reading), [NFC Forum guidance](https://nfc-forum.org/uploads/specifications/NFCForum-AD-CPUX-1.1.pdf), [developer launch example](https://www.scrawlit.com/blog/ios-18-pwa), [reported path loss](https://meta.discourse.org/t/pwa-launched-via-webapp-always-loads-homepage-not-intended-path/375036).
