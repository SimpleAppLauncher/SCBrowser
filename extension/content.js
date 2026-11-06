// SCBrowser Privacy Shield - content script (ISOLATED world)
// In aggressive mode, injects a MAIN-world script that spoofs fingerprint
// surfaces (canvas/WebGL/audio/fonts/navigator). In normal mode, does nothing
// beyond tracker blocking (DNR) - matching ungoogled-chromium defaults.
// Mode is also re-checked live via messages from background.js.

let currentMode = 'normal';
chrome.storage.local.get('mode').then(r => { document.documentElement && document.documentElement.setAttribute('data-sc-mode', r.mode||'none'); console.log('[SC] content mode', r.mode); currentMode = r.mode || 'normal'; if (currentMode === 'aggressive') inject(); }).catch(e=>console.log('[SC] content err', e));

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === 'SC_MODE') {
    const was = currentMode;
    currentMode = msg.mode;
    if (currentMode === 'aggressive' && was !== 'aggressive') inject();
    // Note: spoofing can't be cleanly un-injected without reload; popup warns to reload.
  }
});

function inject() { document.documentElement && document.documentElement.setAttribute('data-sc-inject','called');
  if (document.getElementById('scbrowser-shield')) return;
  // At document_start, documentElement may not exist yet - defer until it does.
  // Appending a <script> to `document` itself never executes it.
  if (!document.documentElement) {
    const obs = new MutationObserver(() => {
      if (document.documentElement) { obs.disconnect(); inject(); }
    });
    obs.observe(document, { childList: true, subtree: true });
    return;
  }
  const s = document.createElement('script');
  s.id = 'scbrowser-shield';
  s.textContent = `
  (function(){
    'use strict';
    // --- deterministic-ish noise (stable per origin so sites don't detect randomness) ---
    function seeded(str){ let h=2166136261; for(let i=0;i<str.length;i++){h^=str.charCodeAt(i); h=Math.imul(h,16777619);} return (h>>>0); }
    const seed = seeded(location.origin);
    function noise(n){ return ((seed + n*2654435761) % 1000)/1000 - 0.5; }
    // Canvas: add tiny noise to pixel reads, block toDataURL fingerprint exfiltration attempts
    try {
      const origGetContext = HTMLCanvasElement.prototype.getContext;
      const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
      const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
      HTMLCanvasElement.prototype.getContext = function(...a){ return origGetContext.apply(this,a); };
      CanvasRenderingContext2D.prototype.getImageData = function(...a){
        const img = origGetImageData.apply(this,a);
        try { const d = img.data; for(let i=0;i<d.length;i+=97){ d[i] = Math.max(0, Math.min(255, d[i] + (noise(i)>0?1:-1))); } } catch(e){}
        return img;
      };
      HTMLCanvasElement.prototype.toDataURL = function(...a){
        // Return a 1x1 blank-ish image for offscreen fingerprint canvases to reduce uniqueness,
        // but let visible canvases still work by falling through for attached canvases with size.
        if (!this.isConnected && this.width <= 300 && this.height <= 300) {
          const c = document.createElement('canvas'); c.width=1; c.height=1;
          return origToDataURL.call(c, ...a);
        }
        return origToDataURL.apply(this,a);
      };
    } catch(e){}
    // WebGL: generic renderer/vendor
    try {
      const origGetParam = WebGLRenderingContext.prototype.getParameter;
      WebGLRenderingContext.prototype.getParameter = function(p){
        if (p === 37445) return 'Generic'; // UNMASKED_VENDOR_WEBGL
        if (p === 37446) return 'Generic GPU'; // UNMASKED_RENDERER_WEBGL
        return origGetParam.apply(this, arguments);
      };
    } catch(e){}
    // Audio fingerprint: add noise to analyser float data
    try {
      const origGetFloat = AnalyserNode.prototype.getFloatFrequencyData;
      if (origGetFloat) AnalyserNode.prototype.getFloatFrequencyData = function(arr){
        origGetFloat.apply(this, arguments);
        for(let i=0;i<arr.length;i+=211){ arr[i] += noise(i)*0.001; }
      };
    } catch(e){}
    // Navigator: reduce uniqueness, hide automation flags
    try {
      Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });
      Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4, configurable: true });
      Object.defineProperty(navigator, 'deviceMemory', { get: () => 4, configurable: true });
      // languages: keep real, but don't add extra entropy
    } catch(e){}
    // Font fingerprint: measureText noise
    try {
      const origMeasure = CanvasRenderingContext2D.prototype.measureText;
      CanvasRenderingContext2D.prototype.measureText = function(t){
        const m = origMeasure.apply(this, arguments);
        try { Object.defineProperty(m, 'width', { get: () => m.width + noise(t.length)*0.1, configurable: true }); } catch(e){}
        return m;
      };
    } catch(e){}
    // Screen: round to coarse buckets
    try {
      Object.defineProperty(window.screen, 'width', { get: () => Math.round(window.screen.width/100)*100, configurable: true });
      Object.defineProperty(window.screen, 'height', { get: () => Math.round(window.screen.height/100)*100, configurable: true });
    } catch(e){}
  })();
  `;
  (document.documentElement || document.head || document).appendChild(s);
  s.remove();
}
