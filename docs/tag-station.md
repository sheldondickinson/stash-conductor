# Tag preparation station

The compiled reference target is **Espressif ESP32 DevKitC V4 with ESP32 WROOM 32**, PlatformIO `esp32dev`, 4 MB flash. This is a selected implementation target, not confirmation of the owner's physical board. Identify that board before connecting wires or flashing; C3, C6, S2 and S3 boards need their own pin/build review. No existing device is flashed by this project.

Jaycar's XC4506 sheet confirms 3.3 V and SPI but does not name the IC. Inspect the actual breakout and IC marking. Firmware accepts MFRC522 version registers 0x91/0x92 and refuses unknown readers. This register check supports commissioning but is not proof of authenticity. NXP documents MFRC522 support for ISO14443 A and NTAG. Use NTAG213 stickers as the baseline; verified NTAG215/216 are also accepted. The included generic MIFARE card/fob must not be assumed to support iPhone URL NDEF use.

ESPHome's standard RC522 component exposes UID and removal events, with no documented Type 2 NDEF write transaction. A UID event cannot prove a URL was written. The small PlatformIO project therefore owns encoding, while Stash owns allocation, arming, history and inventory. Home Assistant is not in the scan path.

## Reference wiring

Disconnect power before wiring. Use 3.3 V only, short wires and a common ground. Match breakout labels rather than assuming physical pin order.

| XC4506 signal | Selected ESP32 DevKitC V4 pin |
| --- | --- |
| VCC | 3V3 |
| GND | GND |
| SCK | GPIO18 |
| MOSI | GPIO23 |
| MISO | GPIO19 |
| NSS / SDA / chip select | GPIO21 |
| RST | GPIO22 |
| IRQ | Unconnected |

GPIO2 is the optional status LED output. DevKitC boards may not have a controllable onboard LED there; an external LED needs an appropriate series resistor. Serial output and Stash status remain sufficient without a screen or buzzer.

## Build and provision

Use a Python virtual environment outside synced data, install PlatformIO and `intelhex`, then:

```sh
pio run -d firmware/tag-station
pio device list
# Only after identifying the dedicated, connected board:
pio run -d firmware/tag-station -t upload --upload-port YOUR_VERIFIED_PORT
pio device monitor --port YOUR_VERIFIED_PORT --baud 115200
```

Dependencies are pinned in `platformio.ini`. The selected Arduino core uses a dual OTA partition layout. Build outputs include firmware, bootloader and partition images; use PlatformIO's uploader for first flash, not the application image alone.

In Stash, create a station as the owner. Save the one time station credential in a protected local file. Provision one compact JSON line over USB serial containing `origin`, `station_id`, `credential`, `ssid`, `wifi_password` and `ca_pem`. `origin` must be the deployed HTTPS origin. `ca_pem` must contain the independently trusted public root certificate(s) needed to validate that hostname, with escaped newlines in JSON. Do not use an unverified certificate fetched from the same untrusted connection. No credential is compiled into firmware or echoed by setup. The station stores its limited credential in ESP32 NVS; flash encryption is not configured, so physical device access requires revocation if lost.

Connect to the approved IoT SSID. Allow only DNS and time synchronisation to the established infrastructure and HTTPS to Stash. This implementation uses an outbound HTTPS API with a revocable station credential, no inbound setup server and no household password. It makes no VLAN changes. Verify the actual firewall rules and DHCP placement during commissioning.

The station starts in `inspect`. Serial commands are `inspect`, `verify`, and `encode`. Inspect and verify both parse without writing. Select `encode`, choose a batch in Stash and explicitly arm the station for five minutes. Switching modes or restarting disarms the local writing path until the next positive server health check; server arming alone does not select encode mode.

## Encoding and recovery

Present one tag. Firmware validates the NXP GET_VERSION layout and capacity, writable capability container, static/dynamic locks and AUTH0. Supported user capacities are 144, 504 and 888 bytes. The compact HTTPS record fits NTAG213. Only user memory from page 4 is written. UID, manufacturer, capability container, lock and configuration pages are preserved; no locks or passwords are enabled.

One UID reserves one unique URL. The reservation is persisted in one NVS record before writing. Firmware first clears the NDEF length, writes payload pages, commits the first page last, reads user memory again, parses the URI and compares it to the reserved URL. Only successful readback is reported as encoded. A lost acknowledgement is recovered using the same reservation and URL; the server never recycles skipped or uncertain identities. A pending reservation blocks the next allocation until verified or explicitly skipped.

The station requires tag removal before another operation. A tag left in the field cannot consume successive URLs. Existing Stash tags are recognised and never automatically overwritten. Other nonblank tags require explicit authorisation for that exact inspected UID; the permission is consumed on verification. Reassignment of a Stash tag is a server operation and does not require rewriting its URL.

A successful readback produces two LED pulses if an LED is connected, and the readable code appears in Stash. Optional label printing has a separate job/status and an idempotent reservation key. Verify the printed label against the code before pairing it with the sticker.

After interruption, remove and present the same tag in encode mode. If its URL already matches the retained reservation, firmware acknowledges without rewriting. For an incomplete write, rearm and retry that reservation. Use the station panel to skip an unrecoverable reservation. It stays in the batch manifest; it is never quietly assigned to another physical tag. The station panel lists recent reservations and can deliberately resume a skipped tag once the current reservation is resolved. Present that same physical tag to keep its original URL.

## Deliberate outbound OTA

Stage the reviewed `firmware.bin` on the backend at `STASH_STATION_FIRMWARE`, normally a read only mount at `/run/stash-station/firmware.bin`. Record its SHA256 independently. Disarm and resolve outstanding reservations. Over USB serial issue `ota SHA256`. The station downloads only its fixed authenticated firmware endpoint over validated HTTPS, checks length and SHA256, then commits the OTA partition and restarts in inspect mode. A mismatch aborts the update. There is no public inbound OTA port. This OTA implementation is compiled, but physical OTA and rollback behaviour still require commissioning.

## Physical checks before a batch

Verify the actual ESP32 model, XC4506 chipset, tag GET_VERSION, capacity and cassette. Test a blank NTAG213; inspect the exact URL after write with an independent phone NFC reader, assign it, and open it signed out and signed in. Leave it on the reader and confirm no second allocation. Interrupt power between write and acknowledgement; confirm the same code survives. Try a nonblank tag, locked tag and incompatible MIFARE card and verify no unwanted writes. Inspect the matching QR label with the target phone. Record these as physical evidence separately from compiled/mock tests.

Plain NTAG stickers work best on nonmetallic surfaces. Metal detunes an ordinary antenna; use a suitable ferrite backed on metal tag or a tested spacer. Test the final mounting position on the actual box. Do not permanently lock during commissioning. The Brother's NFC touch to connect feature pairs a phone with the printer and is not an inventory tag encoder.

Sources: [Jaycar XC4506 sheet](https://media.jaycar.com.au/product/resources/XC4506_datasheetMain_67882.pdf), [NXP MFRC522](https://www.nxp.com/docs/en/data-sheet/MFRC522.pdf), [NXP NTAG21x](https://www.nxp.com/docs/en/data-sheet/NTAG213_215_216.pdf), [ESPHome RC522](https://esphome.io/components/binary_sensor/rc522/), [PlatformIO ESP32 target](https://docs.platformio.org/en/latest/boards/espressif32/esp32dev.html).
