# Brother PT-P750W printing

The application sends server rendered 180 dpi rasters through a narrow Go bridge using `crmin/ptouch-go`, pinned to commit `56074f4aa0b2e74277abd46990d776f65445b9a3` (MIT). The bridge fixes the model to PT-P750W and requires its reported model code, loaded tape and preflight status before sending raster data. It runs on Linux amd64/arm64 or macOS without native dependencies for TCP/SNMP. The Docker image builds the bridge from pinned Go dependencies. No QL driver or browser native print SDK is used.

The selected operational path is private Wi-Fi infrastructure mode, TCP 9100 for printing and SNMP for status, on an existing always on backend host. The trusted operator supplies a private literal IP in a read only mounted JSON file at `/run/stash-printer/config.json`:

```json
{"address":"192.0.2.10","community":"public"}
```

The example documentation IP must be replaced with the actual private printer address. The application rejects public addresses. If the printer uses a different SNMP community, store it in this protected file, never source control or an API request. UI users can change tape/cut preferences and submit structured label jobs; they cannot choose a host, port, executable or printer command. Run the worker with `python manage.py print_worker` sharing the same data directory as the web service. Do not grant a second application simultaneous raw printer access.

For commissioning, identify the actual PT-P750W, note its firmware, disable Editor Lite if applicable, connect its Wi-Fi to the intended private network and reserve its address. Check the cassette in **Printer and queue**, then explicitly print one test label. No connection or physical test is implied by a successful build. A separate agent is unnecessary while the backend can reach the LAN. If hosting later moves offsite, retain this worker at home and design an outbound authenticated job channel; never publish 9100, SNMP or the printer web interface.

## Label dimensions and controls

PT-P750W uses tape up to 24 mm and has a 128 dot print head, approximately 18 mm high at 180 dpi. This release's QR layouts support 18 mm TZe tape (112 printable dots) and 24 mm TZe tape (128 dots). Narrower cassettes are deliberately unsupported for these QR layouts. The saved width is checked against reported cassette width before printing. A missing or incompatible report fails visibly; there is no invented tape status.

The label is approximately 80 mm long including the nominal 2 mm feed at each end. Printer minimum feed/cut behaviour can add physical lead waste. PNG preview and print use the same one bit raster, integer QR modules and four module quiet zones. The QR payload is the stable HTTPS box or tag URL. The tag label's readable code and URL match the registry. Prefer 24 mm for scan margin; physically scan 18 mm samples before producing a batch. SVG exports use exact millimetre dimensions. Print exports at 100 percent with scaling disabled. P touch Editor can import the PNG; set the cassette width and 180 dpi physical size. This remains a fallback.

Available finishing choices are cut each label, half cut each label, or a chain with intermediate half cuts and a final full cut. Open ended chains and experimental pre cut sequences are not exposed. Batch jobs are bounded to 50 physical labels; larger UI batches split into independently identified jobs. Keep tapes appropriate for the chosen cutter mode.

## Queue semantics

`queued` can be cancelled. A serial process lock covers claims, sends and status checks. `sending` cannot reliably be cancelled by this protocol. `completed` means the library observed a job specific print/completion transition, or a user explicitly confirmed all output. `sent_unconfirmed` means bytes were sent without physical completion proof. `outcome_unknown` covers interrupted or uncertain sends. Neither state is automatically retried. Inspect the printer before **Reprint deliberately**. A worker restart changes stale `sending` jobs to unknown; queued jobs older than an hour become held and require explicit resume. Offline or preflight errors become failed with a visible reason.

Job submission uses the existing per user idempotency receipts, while automatic labels after encoding also use a unique reservation key. Repeating a request cannot silently create another physical job. Print settings and immutable label snapshots are stored in the database and included in backups.

## Alternatives assessed

Brother b-PAC is a Windows COM component requiring the supported Windows runtime, matching application bitness and installed Brother driver/SDK. Its model support alone does not provide a Linux, browser or iPhone SDK. No b-PAC runtime, driver redistribution or native phone application is needed here. Brother's current support pages refused automated retrieval during this work, so no Windows deployment or licensing compatibility is claimed. Official P touch Editor remains the user installed fallback on supported Mac/Windows versions.

The `ptouch-print-server` AirPrint project explicitly lists PT-P750W as recognised only; its certified print path is PT-2730, so it was not selected. The chosen library has explicit P750W media, raster, network status and uncertainty handling, with tests run during this integration. That evidence does not establish this household printer's firmware or physical output.

Sources: [Brother raster reference](https://download.brother.com/welcome/docp100064/cv_pte550wp750wp710bt_eng_raster_102.pdf), [selected library](https://github.com/crmin/ptouch-go), [AirPrint project limits](https://github.com/pfa230/ptouch-print-server), [Brother model and b-PAC support](https://support.brother.com/g/b/faqend.aspx?c=us&faqid=faqp00001521_000&lang=en&prod=p750weus).
