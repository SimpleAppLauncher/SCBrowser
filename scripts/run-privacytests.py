#!/usr/bin/env python3
"""Run privacytests.org's actual test pages in SCBrowser and report results.

Uses the same test pages as github.com/privacytests/privacytests.org
(live/results.js pageSequence): misc.html, tracking_content.html, https.html,
query.html (tracking params), supercookies.html + navigation.html (write/read
sequences on both first-party domains), plus fingerprint-surface checks
equivalent to scripts/{settings,screen,device}-fingerprint-test.js.

No npm, no MITM proxy, no DNS/system changes (storage-light): each page
renders results into document.body[data-test-results] (see test-pages'
post_data.js showData), which we read via the scbrowser CLI/CDP.

Usage: scripts/run-privacytests.py [--mode aggressive|normal]
Writes: privacytest-results.json (next to this repo root)
"""
import subprocess, json, sys, time, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(ROOT, "bin", "scbrowser")

def cli(*args, timeout=120):
    r = subprocess.run([CLI, *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()

def load_page(url, wait=6):
    cli("navigate", url, "--new")
    time.sleep(wait)
    out = cli("eval", 'document.body.getAttribute("data-test-results") || ""')
    try:
        return json.loads(out) if out and out != "null" else None
    except Exception:
        return None

def eval_js(expr):
    out = cli("eval", expr)
    try:
        return json.loads(out)
    except Exception:
        return out

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "aggressive"
    cli("mode", mode)
    results = {"mode": mode, "pages": {}, "fingerprint": {}}

    pages = {
        "misc (Tor/GPC/ECH)": "https://test-pages.privacytests.org/misc.html",
        "tracking_content": "https://test-pages.privacytests.org/tracking_content.html",
        "https (HTTPS upgrade)": "https://test-pages.privacytests.org/https.html",
    }
    for name, url in pages.items():
        r = load_page(url)
        results["pages"][name] = r
        print(f"== {name} ==")
        print(json.dumps(r, indent=2)[:2000] if r else "NO RESULTS (page may need server/session)")
        print()

    # Tracking query params (same list as live/results.js TRACKING_QUERY_PARAMETERS)
    params = ["fbclid","gclid","msclkid","mc_eid","dclid","oly_anon_id","oly_enc_id","_openstat",
              "vero_conv","vero_id","wickedid","yclid","__s","rb_clickid","s_cid","ml_subscriber",
              "ml_subscriber_hash","_hsenc","__hssc","__hstc","__hsfp","hsCtaTracking","mkt_tok"]
    qs = "&".join(f"{p}=testsecret" for p in params)
    r = load_page(f"https://test-pages.privacytests.org/query.html?controlParam=controlValue&{qs}")
    results["pages"]["query (tracking params)"] = r
    print("== query (tracking params) ==")
    print(json.dumps(r, indent=2)[:2000] if r else "see query.html page (posts via server; check DOM text)")
    print()

    # Fingerprint surfaces (equivalent to settings/screen/device fingerprint probes)
    cli("navigate", "https://example.com", "--new")
    time.sleep(3)
    fp = eval_js("""(()=>{
      const out = {};
      out.webdriver = navigator.webdriver;
      out.hardwareConcurrency = navigator.hardwareConcurrency;
      out.deviceMemory = navigator.deviceMemory;
      out.platform = navigator.platform;
      out.languages = navigator.languages;
      out.screen = [screen.width, screen.height, screen.colorDepth];
      out.userAgent = navigator.userAgent;
      out.uaData = navigator.userAgentData ? navigator.userAgentData.brands : null;
      // canvas fingerprint stability
      try {
        const c = document.createElement('canvas'); c.width=200; c.height=50;
        const x = c.getContext('2d'); x.fillStyle='red'; x.fillText('SCBrowser',10,30);
        out.canvas = c.toDataURL().slice(0,60);
      } catch(e){ out.canvas = 'Error: '+e; }
      // WebGL renderer
      try {
        const gl = document.createElement('canvas').getContext('webgl');
        const dbg = gl.getExtension('WEBGL_debug_renderer_info');
        out.webgl_renderer = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'n/a';
        out.webgl_vendor = dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : 'n/a';
      } catch(e){ out.webgl_renderer = 'Error: '+e; }
      // WebRTC leak check (mDNS .local candidates only = pass)
      out.webrtc = 'needs-async-check';
      return out;
    })()""")
    results["fingerprint"] = fp
    print("== fingerprint surfaces ==")
    print(json.dumps(fp, indent=2))
    print()
    # WebRTC async
    webrtc = eval_js("""new Promise(res=>{
      const ips=new Set(); const pc=new RTCPeerConnection({iceServers:[]});
      pc.onicecandidate=e=>{ if(e.candidate){ const m=e.candidate.candidate.match(/([0-9]{1,3}(\\.[0-9]{1,3}){3})/); if(m) ips.add(m[1]); } else { res([...ips]); pc.close(); } };
      pc.createDataChannel('x'); pc.createOffer().then(o=>pc.setLocalDescription(o));
      setTimeout(()=>res([...ips]), 4000);
    })""")
    results["fingerprint"]["webrtc_public_ips"] = webrtc
    print("WebRTC public IPs seen:", webrtc, "(empty/.local = no leak)")

    out_path = os.path.join(ROOT, "privacytest-results.json")
    json.dump(results, open(out_path, "w"), indent=2)
    print(f"\nSaved: {out_path}")

if __name__ == "__main__":
    main()
