// SCBrowser Privacy Shield - service worker
// Modes:
//  normal     = ungoogled-chromium defaults: tracker DNR only, no spoofing, cookies as profile set
//  aggressive = tracker DNR + fingerprint spoofing (content.js) + strict privacy settings
// Content script reads mode from chrome.storage.local; popup + `scbrowser mode` set it.

async function applyMode(mode) {
  const aggressive = mode === 'aggressive';
  await chrome.storage.local.set({ mode: aggressive ? 'aggressive' : 'normal' });
  // Toggle DNR rule sets
  try {
    await chrome.declarativeNetRequest.updateEnabledRulesets({
      enableRulesetIds: aggressive ? ['normal_rules', 'aggressive_rules'] : ['normal_rules'],
      disableRulesetIds: aggressive ? [] : ['aggressive_rules']
    });
  } catch (e) { console.warn('DNR toggle failed', e); }

  // Browser privacy settings (chrome.privacy). Best-effort; profile flags in
  // config/privacy-flags.txt are the durable layer (survive restarts).
  const P = chrome.privacy;
  const set = async (api, opts) => { try { await api.set(opts); } catch (e) {} };
  if (P && P.network) {
    // referrers: trim to origin in aggressive, leave default in normal
    await set(P.network.referrersEnabled, { value: !aggressive, scope: 'regular' });
  }
  if (P && P.websites) {
    // third-party cookies blocked in both modes (SCBrowser default); aggressive also
    // blocks third-party storage - some sites break, that's the point of aggressive.
    await set(P.websites.thirdPartyCookiesAllowed, { value: false, scope: 'regular' });
    if (P.websites.thirdPartyStorageAllowed) {
      await set(P.websites.thirdPartyStorageAllowed, { value: !aggressive, scope: 'regular' });
    }
  }
  if (P && P.services) {
    // autofill of passwords/credit cards off in aggressive
    if (P.services.passwordSavingEnabled) {
      await set(P.services.passwordSavingEnabled, { value: !aggressive, scope: 'regular' });
    }
  }
  // Notify open pages so content.js can re-read mode without reload where possible
  try {
    const tabs = await chrome.tabs.query({});
    for (const t of tabs) {
      if (t.id) chrome.tabs.sendMessage(t.id, { type: 'SC_MODE', mode: aggressive ? 'aggressive' : 'normal' }).catch(() => {});
      if (aggressive && t.id && t.url && /^https?:/.test(t.url)) {
        chrome.scripting.executeScript({ target: { tabId: t.id }, world: 'MAIN', func: scSpoof }).catch(() => {});
      }
    }
  } catch (e) {}
}

// Main-world fingerprint + WebRTC spoof (injected via chrome.scripting on
// every tab load in aggressive mode - more reliable than content-script
// document_start injection, which can race DOM creation).
function scSpoof() {
  try {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined, configurable: true });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4, configurable: true });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 4, configurable: true });
  } catch (e) {}
  try {
    const origGetParam = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function (p) {
      if (p === 37445) return 'Generic';
      if (p === 37446) return 'Generic GPU';
      return origGetParam.apply(this, arguments);
    };
  } catch (e) {}
  try {
    const origGetImageData = CanvasRenderingContext2D.prototype.getImageData;
    CanvasRenderingContext2D.prototype.getImageData = function () {
      const img = origGetImageData.apply(this, arguments);
      try { const d = img.data; for (let i = 0; i < d.length; i += 97) d[i] = Math.max(0, Math.min(255, d[i] + (i % 194 === 0 ? 1 : -1))); } catch (e) {}
      return img;
    };
  } catch (e) {}
  try {
    const OrigRTC = window.RTCPeerConnection;
    if (OrigRTC) {
      window.RTCPeerConnection = function (cfg, cons) {
        cfg = cfg || {};
        if (!cfg.iceTransportPolicy) cfg.iceTransportPolicy = 'relay';
        return new OrigRTC(cfg, cons);
      };
      window.RTCPeerConnection.prototype = OrigRTC.prototype;
    }
  } catch (e) {}
}

// Inject spoof on every new page load (aggressive only)
chrome.tabs.onUpdated.addListener(async (tabId, info, tab) => { console.log('[SC] tabUpdated', info.status, tab.url);
  if (info.status !== 'complete' || !tab.url || !/^https?:/.test(tab.url)) return;
  const { mode } = await chrome.storage.local.get('mode');
  if (mode !== 'aggressive') return;
  try {
    await chrome.scripting.executeScript({ target: { tabId }, world: 'MAIN', func: scSpoof });
  } catch (e) {}
});

chrome.runtime.onInstalled.addListener(async () => {
  const { mode } = await chrome.storage.local.get('mode');
  await applyMode(mode || 'normal');
});

chrome.runtime.onStartup.addListener(async () => {
  const { mode } = await chrome.storage.local.get('mode');
  await applyMode(mode || 'normal');
});

// Messages from popup / content / CLI-discovered extension targets
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === 'SC_SET_MODE') {
    applyMode(msg.mode).then(() => sendResponse({ ok: true, mode: msg.mode }));
    return true;
  }
  if (msg && msg.type === 'SC_GET_MODE') {
    chrome.storage.local.get('mode').then(r => sendResponse({ ok: true, mode: r.mode || 'normal' }));
    return true;
  }
});
