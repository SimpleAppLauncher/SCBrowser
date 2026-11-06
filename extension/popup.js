async function init() {
  const { mode } = await chrome.storage.local.get('mode');
  const current = mode || 'normal';
  document.querySelector(`input[value="${current}"]`).checked = true;
  document.getElementById('status').textContent = 'Current: ' + current;
  document.querySelectorAll('input[name="mode"]').forEach(el => {
    el.addEventListener('change', async () => {
      await chrome.runtime.sendMessage({ type: 'SC_SET_MODE', mode: el.value });
      document.getElementById('status').textContent = 'Current: ' + el.value + ' — reload tabs to apply spoofing.';
    });
  });
}
init();
