# INFO — SCBrowser deep dive

> **⚠️ ARCHIVED / BROKEN — no longer maintained.** This repository is
> read-only. See §0 for the post-mortem. Licensed under GPLv3 (see
> [LICENSE](LICENSE)).

## 0. Post-mortem (why this project was archived)

SCBrowser was archived because the core approach did not hold up:

1. **Bundle rebranding vs. code signing.** The original design rebranded
   `Info.plist` and used a shell wrapper as the executable. Chromium's
   Developer ID signature carries a `kill` flag, so any bundle edit
   invalidates it and macOS SIGKILLs every launch. Self-signed identities
   import as untrusted and cannot re-sign it; ad-hoc signing breaks library
   validation. The workaround (byte-identical bundle, CLI-injected flags)
   worked, but left a browser that could never be edited, rebranded, or
   given a custom icon without breaking itself.
2. **Keychain encryption is hardcoded.** Chromium's OSCrypt service name
   (`Chromium Safe Storage`) is baked into the binary — a dedicated
   per-app entry is impossible without a full Chromium source rebuild
   (~150 GB, 16 GB+ RAM). The "relaunch to keep things encrypted" banner
   was a direct consequence of the rebranded identity.
3. **Maintenance cost.** Every Chromium upgrade required a careful rebuild,
   and upgrading while a browser was running broke the running instance.
   GPC (Global Privacy Control) is unfixable on Chromium at the binary
   level (DNR forbids `sec-*` header changes, no GPC pref in ungoogled).
4. **Weight.** On Chromium, ~400 MB footprint after heavy use is the floor,
   not a bug — site-isolated multi-process architecture. Lighter bases
   (Firefox/LibreWolf, WebKit/Orion) trade away the CDP terminal control
   or the MV3 extension model this project depended on.

The code is preserved as-is for reference. If revived, start from a
Firefox-based or WebKit-based design instead of re-wrapping Chromium.

All the nerdy stuff: architecture, signing, Keychain, cold start, flags,
RAM methodology, known limitations, and troubleshooting. For the quick start,
see [README.md](README.md).

> Last verified: Chromium 156.0.8078.79, macOS arm64, 2026-11-06.

---

## 1. Architecture

```
~/SCBrowser/
  SCBrowser.app/            # byte-identical copy of /Applications/Chromium.app (built, never edited)
  bin/scbrowser             # CLI — Python 3 stdlib only (HTTP CDP + minimal WebSocket client)
  extension/                # Privacy Shield (MV3) — loaded from here, outside the bundle
  config/privacy-flags.txt  # one flag per line, read by the CLI at every launch
  scripts/build-app.sh      # rebuild SCBrowser.app from /Applications/Chromium.app
  scripts/install.sh        # full install: Brew + build + PATH symlink + verify
  scripts/measure.sh        # RAM measurement on a video site
  scripts/make-comparison.py# regenerates comparison.html from privacytests.org data
  scripts/run-privacytests.py
  assets/                   # logo.png, icon-1024.png, SCBrowser.icns (see §9)
  comparison.html           # privacytests.org comparison page
  scbrowser.log             # Chromium stdout/stderr
Profile: ~/Library/Application Support/SCBrowser  (created on first launch)
```

Launch chain: `scbrowser open` → Python CLI spawns
`SCBrowser.app/Contents/MacOS/Chromium` directly with
`--user-data-dir=~/Library/Application Support/SCBrowser`,
`--remote-debugging-port=9222`, `--load-extension=~/SCBrowser/extension`,
`--window-size/position`, `--start-maximized`, plus every flag from
`config/privacy-flags.txt`. It waits for DevTools on `127.0.0.1:9222`
(`wait_ready`, fails fast if the process dies), then minimizes the window
via AppleScript targeting SCBrowser only. `show` re-activates it.

The CLI resolves its own location with `os.path.realpath(__file__)` so it
works both as `./bin/scbrowser` and as the `/usr/local/bin/scbrowser`
symlink. (An earlier `abspath` version broke under the symlink — symptom:
"SCBrowser.app not built" pointing at `/usr/local`.)

`close` uses CDP `Browser.close` with a scoped fallback that only kills
processes whose command line contains `SCBrowser.app`. It never touches
`/Applications/Chromium.app` or your regular Chromium.

## 2. The signing rule (read this before touching the bundle)

**`SCBrowser.app` must stay byte-identical to the signed original.**

- Chromium's main binary is Developer ID signed (Qian Qian, B9A88FL5XJ) with
  the `kill,restrict,library-validation,runtime` flags.
- Changing `Info.plist` (name, bundle ID, executable), adding a wrapper script
  as `CFBundleExecutable`, adding files inside the bundle, or re-signing
  invalidates the signature → macOS AMFI **SIGKILLs every exec** (`-9`,
  empty log, no window). `codesign --verify` then reports
  `invalid Info.plist` / `no usable signature`.
- Self-signed "SCBrowser Dev" identities import as `CSSMERR_TP_NOT_TRUSTED`
  (0 valid codesigning identities), so `codesign --sign` cannot use them.
  Ad-hoc deep signing (`codesign -s -`) was tried and makes it worse
  (library validation fails against ad-hoc signatures on arm64).
- What looks like "intermittent 137 on first launches" is stale trustd
  validation cache: after a bundle modification, execs are killed until the
  cache revalidates — and if the signature is permanently invalid, it never
  recovers. Persistent `-9` + empty log = invalid signature, not a slow start.

Consequences (all deliberate):
- The bundle keeps its original name/ID/executable (`Chromium`).
- Identity comes from **launch flags**, not the bundle.
- **Launch via the CLI only.** Double-clicking the `.app` opens stock
  Chromium with the default profile.
- `build-app.sh` = `cp -a` + `xattr -cr` + verify (`codesign --verify`,
  `spctl -a`) + `--version` warm-up. Nothing else. Ever.

## 3. Keychain encryption ("Relaunch to keep things encrypted")

Chromium's OSCrypt on macOS uses a **fixed service name baked into the
binary** (`Chromium Safe Storage` — verified by scanning the framework
binary; there is exactly one such string). It is not derived from the bundle
ID and cannot be changed at runtime. A dedicated "SCBrowser Safe Storage"
entry would simply never be looked up. The only way to rename it is a
Chromium source rebuild (~150 GB disk, 16 GB+ RAM, days of compile —
not feasible on an 8 GB Mac with 38 GB free).

How the bug happened and was fixed:
1. Rebranding the bundle changed its designated requirement, so the Keychain
   ACL denied access to the existing `Chromium Safe Storage` item
   (`-25293 errKCAuthFailed`) → OSCrypt reported "Encryption is not
   available" → the banner looped forever (every relaunch re-denied).
2. Restoring the original signed `Info.plist` made the identity match the
   ACL again. New launches log **no** keychain errors, and no manual
   "Always Allow" click or ACL hack is needed. Your real Chromium's Keychain
   item was never modified.
3. The mock keychain (`--use-mock-keychain` / `--password-store=basic`) stays
   **off** — it would "fix" the banner by not encrypting at all, and it
   breaks passkeys. Real passkeys (Touch ID, iCloud Keychain, QR hybrid)
   need the real Keychain.

Note: the `NSBluetoothAlwaysUsageDescription` key originally added for QR
passkeys lived in the same `Info.plist` that broke the signature, so it was
removed with the restore. Stock ungoogled-chromium ships without it; Touch
ID passkeys are unaffected. If QR-hybrid Bluetooth discovery ever misbehaves,
that's the known tradeoff — fixing it properly requires an Apple-signed
build, not a plist edit.

## 4. GPU sandbox

`--disable-gpu-sandbox` used to be in `config/privacy-flags.txt` (added early
for Apple Silicon GPU sandbox instability). It was **removed**: the GPU
process now runs with Seatbelt (`--seatbelt-client=...`) and hardware
acceleration works. `--ignore-gpu-blocklist` is retained. The GPU sandbox is
a real security boundary (GPU process parsing) — don't re-add the flag
unless GPU crashes return.

## 5. Cold start

Measured on this Mac (Apple Silicon, 8 GB RAM):

| Scenario | Time | Result |
|---|---|---|
| Broken signature (rebranded plist + wrapper) | 9.4 s | **fail** — SIGKILL `-9` ×4 retries |
| Fixed (byte-identical bundle, CLI launches binary) | 2.4–4.5 s | pass |
| After 154 → 156 upgrade (profile migration) | ~6–7 s | pass, under the 10 s goal |

The CLI itself is not the bottleneck (Python startup ≈ 0.025 s,
`scbrowser status` ≈ 0.08 s) — which is why a Rust rewrite of the launcher
was rejected: it would save milliseconds while the real cost was signature
validation and profile load. `wait_ready` is 30 s with fail-fast on process
death and a 60 s grace wait if the process is alive but DevTools is slow
(possible modal dialog — run `scbrowser show` to look).

## 6. Flags reference (`config/privacy-flags.txt`)

- Startup/updates: `--no-first-run`, `--no-default-browser-check`,
  `--disable-default-apps`, `--disable-component-update`,
  `--disable-background-networking`, `--disable-sync`, `--disable-translate`,
  `--disable-hang-monitor`, `--disable-prompt-on-repost`,
  `--disable-field-trial-config`, `--disable-breakpad`,
  `--metrics-recording-only`, `--no-pings`,
  `--disable-client-side-phishing-detection`,
  `--safebrowsing-disable-download-protection`,
  `--disable-session-crashed-bubble`.
- RAM caps: `--renderer-process-limit=2`,
  `--js-flags=--max-old-space-size=256`,
  `--disk-cache-size=52428800`, `--media-cache-size=52428800`.
- GPU: `--ignore-gpu-blocklist` (sandbox restored, see §4).
- Privacy: `--webrtc-ip-handling-policy=disable-non-proxied-udp` (+ forced),
  `--fingerprinting-canvas-image-noise`,
  `--fingerprinting-canvas-measure-noise`,
  `--fingerprinting-client-rects-noise`, `--enable-do-not-track`,
  `--disable-privacy-sandbox`, and a single combined
  `--disable-features=Translate,MediaRouter,DialMediaRouteProvider,OptimizationHints,OptimizationGuideModelDownloading,OptimizationGuideOnDeviceModel,InterestHints,PrivacySandbox,CalculateNativeWinOcclusion,WebBluetooth,WebUSB,WebSerial,WebHID,FileSystemAccessAPI,Printing,DesktopSharingHub,DnsOverHttps,ThirdPartyCookiePhaseout`
  (duplicated `--disable-features` flags override each other — keep it one).
- Extension: `--enable-unsafe-extension-debugging` (required on current
  Chromium for `--load-extension` to take effect).
- Explicitly absent: `--use-mock-keychain`, `--password-store=basic`,
  `--disable-gpu-sandbox` — see §3 and §4.

Chromium ignores unknown flags with a warning, so flags surviving a version
bump are low-risk; after an upgrade, re-run `scbrowser status` and check
`scbrowser.log` for new errors.

## 7. Privacy Shield extension (`extension/`, MV3)

- **Normal** (default): `rules_normal.json` tracker blocking only
  (GA, GTM, DoubleClick, FB, Hotjar, FullStory, Segment, Mixpanel,
  Amplitude, Sentry). No fingerprint spoofing.
- **Aggressive**: normal + `rules_aggressive.json` (fingerprint/tracker
  domains) + main-world spoofing from `content.js` (canvas noise, generic
  WebGL vendor/renderer, audio analyser noise, reduced `navigator` entropy,
  font-measure noise, coarse screen) + strict `chrome.privacy` settings via
  `background.js`. Reload tabs after switching.
- `scbrowser mode aggressive|normal` drives it through the extension service
  worker over CDP (`Target.getTargets` attach). One bad rule in a ruleset
  (e.g. a wildcard `||*.ads.`) kills the whole MV3 extension — validate
  rulesets after editing.
- Fingerprint spoofing caveat: main-world injection races page scripts
  (document_start ordering), so `navigator.hardwareConcurrency`-style
  values may not stick on every page. Treat spoofing as best-effort, not a
  guarantee.

## 8. privacytests.org results & known limitations

Tested via CDP against the official pages (`scripts/run-privacytests.py`,
results in `privacytest-results.json`; comparison in `comparison.html`):

- ✅ ECH (Encrypted Client Hello)
- ✅ HTTPS-upgrade (image + script)
- ✅ `navigator.webdriver === false`
- ✅ WebRTC: no public-IP leak (private `192.168.x` only)
- ❌ GPC (Global Privacy Control): Chromium forbids DNR modification of
  `sec-*` headers and ungoogled-chromium has no GPC preference — **not
  fixable without a Chromium source patch**. A `sec-gpc` DNR rule exists but
  is ineffective.
- ❌ Tor: excluded by design (Tor Browser is a separate product).
- ⚠️ Canvas/WebGL spoofing: unreliable via JS injection (see §7).

IP/DNS leak results also depend on your network (VPN etc.) — browser flags
stop non-proxied UDP leaks; they can't fix a non-VPN network.

Regenerate the comparison after re-running tests:
`python3 scripts/make-comparison.py` (needs a fresh
`https://privacytests.org/index.json`).

## 9. Icon & branding

`assets/` contains the cropped logo (`logo.png`, `icon-1024.png`) — cropped
from the original artwork by detecting the blue "S" bounding box
(2048×2048 → square crop, ~18% padding) — plus `assets/SCBrowser.icns`
(16–1024 px, built with `iconutil`). The extension icons
(`extension/icons/icon{16,48,128}.png`) were regenerated from the same crop.

The `.icns` is **not** installed into `SCBrowser.app`: replacing
`Contents/Resources/app.icns` breaks the sealed-resources signature (§2).
The app therefore still shows Chromium's icon in Finder/Dock. Installing the
custom icon properly requires an Apple-signed build. The logo is used in the
README and extension, where it is signature-safe.

## 10. RAM methodology

`scbrowser status`/`memory` walks the process tree from the SCBrowser main
process (helpers carry no profile in argv) and sums RSS. **RSS sums
double-count shared framework pages** across ~10 Chromium processes, so the
CLI also reports physical footprint via `footprint` — footprint is the
honest number. Light sites: ~90 MB main-process footprint. YouTube homepage
settled ~235 MB RSS-sum in one run, ~420 MB footprint after many
navigations. <400 MB footprint is realistic for light sites and low-res
YouTube with 1 tab; 1080p playback exceeds it in any Chromium browser.
Knobs: fewer tabs, lower resolution, `--renderer-process-limit=1`.

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Browser failed to start`, `-9`, empty log | Invalid signature (§2) | `./scripts/build-app.sh` (fresh byte-identical copy). Never edit/re-sign the bundle. |
| "Relaunch to keep things encrypted" | Keychain ACL denial (§3) | Same as above — signature restore fixes it. Don't add mock-keychain flags. |
| `scbrowser: command not found` | Not on PATH | `ln -sf ~/SCBrowser/bin/scbrowser /usr/local/bin/scbrowser`, or `export PATH="$HOME/SCBrowser/bin:$PATH"` in `~/.zshrc`, then `rehash`. |
| "SCBrowser.app not built" pointing at `/usr/local` | CLI root resolved via symlink | Fixed: CLI uses `realpath(__file__)`. Update `bin/scbrowser`. |
| Extension won't load / mode switch fails | Bad ruleset rule or missing `--enable-unsafe-extension-debugging` | Validate `extension/rules_*.json`; keep the flag; `scbrowser mode aggressive` to test. |
| Slow first launch after rebuild/upgrade | trustd revalidation + profile migration | Wait and retry; expect ~6 s. Persistent `-9` = signature, not slowness. |
| Modal dialog blocks DevTools | Profile lock (second instance on same profile) | `scbrowser show` to look; `scbrowser close` before relaunching. |
| GPU crash after flag changes | Sandbox/blocklist interaction | Keep `--ignore-gpu-blocklist`, keep `--disable-gpu-sandbox` **out** (§4). |

## 12. Updating Chromium

1. `brew upgrade --cask ungoogled-chromium` (replaces
   `/Applications/Chromium.app`; your Chromium data is preserved).
2. `scbrowser close`
3. `cd ~/SCBrowser && ./scripts/build-app.sh` — verifies signature, runs
   `--version` warm-up (must pass first try).
4. `scbrowser open https://example.com && scbrowser status` — check version,
   tabs, and that `scbrowser.log` has no new errors.

Never `codesign --force --deep --sign -` the bundle as a "fix" (see §2).
