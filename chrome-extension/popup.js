// popup.js — Chrome Extension Bug Bounty Scanner

const DEFAULT_API = "https://bugbounty-api.onrender.com";

async function getApiBase() {
  return new Promise(r => chrome.storage.local.get("api_base", d =>
    r(d.api_base || DEFAULT_API)
  ));
}

async function getLastSession() {
  return new Promise(r => chrome.storage.local.get("last_session_id", d =>
    r(d.last_session_id || null)
  ));
}

function setStatus(msg, type = "") {
  const box = document.getElementById("status-box");
  box.innerHTML = msg;
}

function badge(text, type) {
  return `<span class="badge badge-${type}">${text}</span>`;
}

// Tampilkan URL tab aktif
chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
  const url = tabs[0]?.url || "";
  document.getElementById("current-url").textContent = url;
});

// Tampilkan provider AI aktif
(async () => {
  const base = await getApiBase();
  try {
    const r = await fetch(`${base}/api/ai/provider`);
    const d = await r.json();
    document.getElementById("provider-badge").textContent = `provider: ${d.provider}`;
  } catch {
    document.getElementById("provider-badge").textContent = "provider: offline";
  }
})();

// ─── Tombol Scan ─────────────────────────────────────────────────────────────
document.getElementById("btn-scan").addEventListener("click", async () => {
  const btn = document.getElementById("btn-scan");
  btn.disabled = true;
  setStatus("⏳ Mendaftarkan target...");

  const base = await getApiBase();
  const [tab] = await new Promise(r => chrome.tabs.query({ active: true, currentWindow: true }, r));
  const url = new URL(tab.url);
  const baseUrl = `${url.protocol}//${url.hostname}`;

  try {
    // 1. Tambah target (atau pakai existing)
    const targetRes = await fetch(`${base}/api/targets`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nama: url.hostname,
        jenis: document.getElementById("target-type").value,
        base_url: baseUrl,
        deskripsi: `Auto-added dari Chrome Extension: ${tab.url}`,
      }),
    });
    const target = await targetRes.json();

    // 2. Mulai scan
    const scanRes = await fetch(`${base}/api/scan/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_id: target.id,
        session_name: `Scan ${url.hostname}`,
        severity_filter: document.getElementById("severity").value,
        use_ai_triage: document.getElementById("use-ai").value === "true",
      }),
    });
    const scan = await scanRes.json();

    chrome.storage.local.set({ last_session_id: scan.session_id });

    setStatus(`
      Scan dimulai! ${badge("running", "run")}<br>
      <b>Target:</b> ${baseUrl}<br>
      <b>Session:</b> <code>${scan.session_id.slice(0, 8)}…</code><br>
      <small>Klik "Cek Status" untuk update</small>
    `);
  } catch (e) {
    setStatus(`${badge("error", "err")} Gagal: ${e.message}<br><small>Pastikan API aktif & URL benar di Settings</small>`);
  }

  btn.disabled = false;
});

// ─── Tombol Status ────────────────────────────────────────────────────────────
document.getElementById("btn-status").addEventListener("click", async () => {
  const base = await getApiBase();
  const sessionId = await getLastSession();

  if (!sessionId) {
    setStatus("Belum ada scan yang dijalankan.");
    return;
  }

  try {
    const r = await fetch(`${base}/api/scan/status/${sessionId}`);
    const d = await r.json();

    const statusBadge = {
      pending:   badge("pending", "warn"),
      running:   badge("running", "run"),
      completed: badge("selesai", "ok"),
      failed:    badge("gagal", "err"),
    }[d.status] || badge(d.status, "warn");

    setStatus(`
      Status: ${statusBadge}<br>
      <b>Temuan:</b> ${d.total_findings || 0}<br>
      <b>Session:</b> <code>${sessionId.slice(0, 8)}…</code><br>
      <small>${d.notes || ""}</small>
    `);
  } catch (e) {
    setStatus(`${badge("error", "err")} Gagal fetch status: ${e.message}`);
  }
});

// ─── Settings link ────────────────────────────────────────────────────────────
document.getElementById("open-options").addEventListener("click", async e => {
  e.preventDefault();
  const current = await getApiBase();
  const newBase = prompt("API Base URL:", current);
  if (newBase) {
    chrome.storage.local.set({ api_base: newBase.replace(/\/$/, "") });
    setStatus(`✅ API URL disimpan: ${newBase}`);
  }
});
