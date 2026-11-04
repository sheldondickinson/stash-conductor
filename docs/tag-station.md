# Tag preparation station

The selected target is the owner's **ESP32 C3 SuperMini**, with ESP32 C3 and 4 MB flash. PlatformIO uses the `esp32-c3-devkitm-1` chip/flash profile, explicit SuperMini GPIO mapping and native USB Serial/JTAG. It is compiled as environment `esp32c3-supermini`. An S3 is unnecessary for this small station. Confirm the board marking, flash size and labelled pads before first flash; SuperMini clones can differ. No existing device is flashed by this project.

Jaycar's XC4506 sheet confirms 3.3 V and SPI but does not name the IC. Inspect the actual breakout and IC marking. Firmware accepts MFRC522 version registers 0x91/0x92 and refuses unknown readers. This register check supports commissioning but is not proof of authenticity. NXP documents MFRC522 support for ISO14443 A and NTAG. Use NTAG213 stickers as the baseline; verified NTAG215/216 are also accepted. The included generic MIFARE card/fob must not be assumed to support iPhone URL NDEF use.

ESPHome's standard RC522 component exposes UID and removal events, with no documented Type 2 NDEF write transaction. A UID event cannot prove a URL was written. The small PlatformIO project therefore owns encoding, while Stash owns allocation, arming, history and inventory. Home Assistant is not in the scan path.

## ESP32 C3 SuperMini wiring

Disconnect power before wiring. Use 3.3 V only, short wires and a common ground. Match breakout labels rather than assuming physical pin order.

| XC4506 signal | ESP32 C3 SuperMini labelled GPIO |
| --- | --- |
| VCC | 3V3 |
| GND | GND |
| SCK | GPIO4 |
| MOSI | GPIO6 |
| MISO | GPIO5 |
| NSS / SDA / chip select | GPIO7 |
| RST | GPIO10 |
| IRQ | Unconnected |

The common SuperMini onboard blue LED is active low on GPIO8. Firmware drives it only after boot and uses it for success pulses. GPIO8 is a strapping pin, so do not attach an extra load. The reader avoids GPIO2, GPIO8 and GPIO9 strapping pins and leaves GPIO18/19 for USB. Check the board's actual LED; serial output and Stash status remain available if a clone differs. A screen or buzzer is unnecessary.

## Build and provision

Use a Python virtual environment outside synced data, install PlatformIO and `intelhex`, then:

```sh
pio run -d firmware/tag-station -e esp32c3-supermini
pio device list
# Only after identifying the dedicated, connected board:
pio run -d firmware/tag-station -e esp32c3-supermini -t upload --upload-port YOUR_VERIFIED_PORT
pio device monitor --port YOUR_VERIFIED_PORT --baud 115200
```

Use a data capable USB cable. If first upload does not enter download mode, hold BOOT, tap RESET, release BOOT, then identify the new USB port before retrying. Native USB is enabled for serial setup. Do not connect the reader to 5 V.

Dependencies are pinned in `platformio.ini`. The selected Arduino core uses a dual OTA partition layout. Build outputs include firmware, bootloader and partition images; use PlatformIO's uploader for first flash, not the application image alone.

In Stash, create a station as the owner. Save the one time station credential in a protected local file. Provision one compact JSON line over USB serial containing `origin`, `station_id`, `credential`, `ssid`, `wifi_password`, `ntp_server` and `ca_pem`. `origin` must be the deployed HTTPS origin. `ca_pem` must contain the independently trusted public root certificate(s) needed to validate that hostname, with escaped newlines in JSON. Do not use an unverified certificate fetched from the same untrusted connection. No credential is compiled into firmware or echoed by setup. The station stores its limited credential in ESP32 NVS; flash encryption is not configured, so physical device access requires revocation if lost.

Set `ntp_server` to the approved local time server; the fallback is `pool.ntp.org`. Connect to the approved IoT SSID. Allow only DNS and time synchronisation to the established infrastructure and HTTPS to Stash. This implementation uses an outbound HTTPS API with a revocable station credential, no inbound setup server and no household password. It makes no VLAN changes. Verify the actual firewall rules and DHCP placement during commissioning.

On boot the station reports its restart and disarms its server allocation path. Once it appears connected, select a batch in Stash and explicitly arm it for five minutes. Normal batches need no USB command after setup. Every physical write still requires a fresh successful armed response and reservation.

Optional serial commands `inspect` and `verify` both parse without writing, even if someone arms the station in Stash. `encode` restores normal server controlled operation. Switching modes disarms locally until the next positive health check. A restart clears the previous server arm and preserves any outstanding reservation.

## Encoding and recovery

Present one tag. Firmware validates the NXP GET_VERSION layout and capacity, writable capability container, static/dynamic locks and AUTH0. Supported user capacities are 144, 504 and 888 bytes. The compact HTTPS record fits NTAG213. Only user memory from page 4 is written. UID, manufacturer, capability container, lock and configuration pages are preserved; no locks or passwords are enabled.

One UID reserves one unique URL. The reservation is persisted in one NVS record before writing. Firmware first clears the NDEF length, writes payload pages, commits the first page last, reads user memory again, parses the URI and compares it to the reserved URL. Only successful readback is reported as encoded. A lost acknowledgement is recovered using the same reservation and URL; the server never recycles skipped or uncertain identities. A pending reservation blocks the next allocation until verified or explicitly skipped.

The station requires tag removal before another operation. A tag left in the field cannot consume successive URLs. Existing Stash tags are recognised and never automatically overwritten. Other nonblank tags require explicit authorisation for that exact inspected UID; the permission is consumed on verification. Reassignment of a Stash tag is a server operation and does not require rewriting its URL.

A successful readback produces two LED pulses if an LED is connected, and the readable code appears in Stash. Optional label printing has a separate job/status and an idempotent reservation key. Verify the printed label against the code before pairing it with the sticker.

After interruption, remove and present the same tag in encode mode. If its URL already matches the retained reservation, firmware acknowledges without rewriting. For an incomplete write, rearm and retry that reservation. Use the station panel to skip an unrecoverable reservation. It stays in the batch manifest; it is never quietly assigned to another physical tag. The station panel lists recent reservations and can deliberately resume a skipped tag once the current reservation is resolved. Present that same physical tag to keep its original URL.

## Deliberate outbound OTA

Stage the reviewed `firmware.bin` on the backend at `STASH_STATION_FIRMWARE`, normally a read only mount at `/run/stash-station/firmware.bin`. Record its SHA256 independently. Disarm and resolve outstanding reservations. Over USB serial issue `ota SHA256`. The station downloads only its fixed authenticated firmware endpoint over validated HTTPS, checks length and SHA256, then commits the OTA partition and restarts disarmed. A mismatch aborts the update. There is no public inbound OTA port. This OTA implementation is compiled, but physical OTA and rollback behaviour still require commissioning.

## Physical checks before a batch

Verify the actual ESP32 model, XC4506 chipset, tag GET_VERSION, capacity and cassette. Test a blank NTAG213; inspect the exact URL after write with an independent phone NFC reader, assign it, and open it signed out and signed in. Leave it on the reader and confirm no second allocation. Interrupt power between write and acknowledgement; confirm the same code survives. Try a nonblank tag, locked tag and incompatible MIFARE card and verify no unwanted writes. Inspect the matching QR label with the target phone. Record these as physical evidence separately from compiled/mock tests.

Plain NTAG stickers work best on nonmetallic surfaces. Metal detunes an ordinary antenna; use a suitable ferrite backed on metal tag or a tested spacer. Test the final mounting position on the actual box. Do not permanently lock during commissioning. The Brother's NFC touch to connect feature pairs a phone with the printer and is not an inventory tag encoder.

Sources: [Jaycar XC4506 sheet](https://media.jaycar.com.au/product/resources/XC4506_datasheetMain_67882.pdf), [NXP MFRC522](https://www.nxp.com/docs/en/data-sheet/MFRC522.pdf), [NXP NTAG21x](https://www.nxp.com/docs/en/data-sheet/NTAG213_215_216.pdf), [ESPHome RC522](https://esphome.io/components/binary_sensor/rc522/), [Espressif C3 hardware guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32c3/schematic-checklist.html), [SuperMini vendor schematic](https://dl.artronshop.co.th/ESP32-C3%20SuperMini%20datasheet.pdf), [SuperMini supplier pin guide](https://www.auscomtech.com.au/support/guides/esp32-c3-supermini-development-board-arduino-setup-pinout-wifi-troubleshooting/).
