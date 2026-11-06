#!/usr/bin/env python3
"""Generate comparison.html: SCBrowser vs privacytests.org desktop browsers.
Data: https://privacytests.org/index.json (official results, latest run per
browser) + ~/SCBrowser/privacytest-results.json (our run via run-privacytests.py).
No extra storage: output is a single self-contained HTML file.
"""
import json, os, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PT = json.load(open("/tmp/pt.json")) if os.path.exists("/tmp/pt.json") else {"all_tests": []}
OURS = json.load(open(os.path.join(ROOT, "privacytest-results.json"))) if os.path.exists(os.path.join(ROOT, "privacytest-results.json")) else {}

# Latest run per browser (last entry wins)
latest = {}
for t in PT.get("all_tests", []):
    latest[t["browser"]] = t["testResults"]

# Flatten official results: {(browser, category, test): passed|None}
official = {}
for browser, tr in latest.items():
    for cat, tests in tr.items():
        if not isinstance(tests, dict):
            continue
        for name, res in tests.items():
            if isinstance(res, dict) and "passed" in res:
                official[(browser, cat, name)] = res["passed"]
            elif isinstance(res, dict):
                official[(browser, cat, name)] = res.get("passed")

# Our results mapped to same categories where we ran the same test pages
ours = {}
misc = OURS.get("pages", {}).get("misc (Tor/GPC/ECH)")
if isinstance(misc, str):
    try: misc = json.loads(misc)
    except Exception: misc = None
if misc:
    for name, res in misc.items():
        ours[("misc", name)] = res.get("passed")
https = OURS.get("pages", {}).get("https (HTTPS upgrade)")
if isinstance(https, str):
    try: https = json.loads(https)
    except Exception: https = None
if https:
    for name, res in https.items():
        ours[("https", name)] = res.get("passed")
fp = OURS.get("fingerprint", {})
if fp:
    ours[("fingerprinting", "webdriver hidden")] = fp.get("webdriver") is False
    ours[("fingerprinting", "WebGL renderer genericized")] = fp.get("webgl_renderer") in ("Generic GPU", "Generic")
    ours[("fingerprinting", "CPU cores genericized (4)")] = fp.get("hardwareConcurrency") == 4
    webrtc = fp.get("webrtc_public_ips")
    if webrtc is not None:
        ours[("fingerprinting", "WebRTC no public IP leak")] = len([x for x in webrtc if not x.startswith(("192.168.", "10.", "172."))]) == 0

browsers = ["scbrowser", "ungoogled", "brave", "firefox", "librewolf", "mullvad", "duckduckgo", "chrome", "edge", "safari", "opera", "vivaldi", "tor"]
labels = {"scbrowser": "SCBrowser (ours)", "ungoogled": "Ungoogled Chromium", "brave": "Brave", "firefox": "Firefox",
          "librewolf": "LibreWolf", "mullvad": "Mullvad", "duckduckgo": "DuckDuckGo", "chrome": "Chrome",
          "edge": "Edge", "safari": "Safari", "opera": "Opera", "vivaldi": "Vivaldi", "tor": "Tor Browser"}

# All (category, test) pairs from official data, ordered
pairs = []
seen = set()
for (browser, cat, name) in official:
    if (cat, name) not in seen:
        seen.add((cat, name)); pairs.append((cat, name))
pairs.sort()
# Add our extra fingerprint tests
for (cat, name) in sorted(ours):
    if (cat, name) not in seen:
        pairs.append((cat, name)); seen.add((cat, name))

def cell(browser, cat, name):
    if browser == "scbrowser":
        v = ours.get((cat, name), "NT")
    else:
        v = official.get((browser, cat, name), "NT")
    if v is True: return '<span class="pass">✓</span>'
    if v is False: return '<span class="fail">✗</span>'
    if v is None: return '<span class="unsup">—</span>'
    return '<span class="nt">·</span>'

rows = []
for cat, name in pairs:
    tds = "".join(f"<td>{cell(b, cat, name)}</td>" for b in browsers)
    rows.append(f'<tr><td class="cat">{html.escape(cat)}</td><td>{html.escape(name)}</td>{tds}</tr>')

# Scores per browser (official categories only, latest run)
def score(browser):
    vals = [v for (b, c, n), v in official.items() if b == browser and isinstance(v, bool)]
    return (sum(vals), len(vals)) if vals else (0, 0)
score_row = ""
for b in browsers:
    if b == "scbrowser":
        vals = [v for v in ours.values() if isinstance(v, bool)]
        score_row += f"<td><b>{sum(vals)}/{len(vals)}</b> tested</td>"
    else:
        p, n = score(b)
        score_row += f"<td>{p}/{n}</td>"

page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>SCBrowser vs privacytests.org</title>
<style>body{{font-family:-apple-system,system-ui,sans-serif;margin:24px;background:#f7f7f5;color:#111}}
h1{{font-size:20px}} .sub{{color:#555;font-size:13px;margin-bottom:12px}}
table{{border-collapse:collapse;font-size:12px;background:#fff}} th,td{{border:1px solid #ddd;padding:4px 6px;text-align:center}}
th{{background:#111;color:#fff;position:sticky;top:0}} td:nth-child(2){{text-align:left}}
.sc{{background:#e6f4ea}} .pass{{color:#137333;font-weight:700}} .fail{{color:#c5221f;font-weight:700}}
.unsup{{color:#888}} .nt{{color:#bbb}} .cat{{color:#666;font-size:11px}}
.legend{{font-size:12px;color:#444;margin:8px 0}}</style></head><body>
<h1>🛡️ SCBrowser vs PrivacyTests.org (Desktop)</h1>
<div class="sub">Official data: privacytests.org/index.json (latest run per browser, updated 2026-10-22) · SCBrowser data: our run via scripts/run-privacytests.py on the same test pages (mode: {html.escape(str(OURS.get('mode','?')))}) · ✓ pass · ✗ fail · — unsupported · · not tested by our runner</div>
<div class="legend">SCBrowser is based on ungoogled-chromium — compare its column with Ungoogled. Tor/GPC/fingerprint rows: see README limitations (GPC needs a Chromium source patch; Tor is expected-fail by design).</div>
<table><tr><th>Category</th><th>Test</th>{''.join(f'<th class="{"sc" if b=="scbrowser" else ""}">{labels[b]}</th>' for b in browsers)}</tr>
<tr><td colspan="2"><b>Passed / tested</b></td>{score_row}</tr>
{''.join(rows)}
</table>
<p class="sub">Generated by scripts/make-comparison.py · Source: github.com/privacytests/privacytests.org · SCBrowser results: privacytest-results.json</p>
</body></html>"""
out = os.path.join(ROOT, "comparison.html")
open(out, "w").write(page)
print(f"Wrote {out} ({len(page)} bytes, {len(pairs)} test rows, {len(browsers)} browsers)")
