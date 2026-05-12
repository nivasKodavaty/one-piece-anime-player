// ============================================================
// One Piece Anime Player — Scriptable Script (v4)
// ============================================================
// Powered by your self-hosted Anime Scraper API.
// Receives episode number → fetches m3u8 stream → opens VLC.
// ============================================================

// ─── CONFIGURATION ──────────────────────────────────────────
const CONFIG = {
  // Your deployed API URL (change after deploying to Render)
  // Local testing: "http://YOUR_MAC_IP:3030"
  // Production:    "https://your-api.onrender.com"
  API_BASE: "https://one-piece-anime-player.onrender.com",

  // Anime slug on Gogoanime/Anitaku
  ANIME_ID: "one-piece",

  // Retry settings (Render free tier cold-start = ~30s)
  MAX_RETRIES: 3,
  RETRY_DELAY_MS: 8000,
  TIMEOUT_SECONDS: 45,
};

// ─── HELPERS ────────────────────────────────────────────────

async function showAlert(title, message) {
  const a = new Alert();
  a.title = title;
  a.message = String(message);
  a.addAction("OK");
  await a.presentAlert();
}

function notify(title, body) {
  const n = new Notification();
  n.title = title;
  n.body = body;
  n.schedule();
}

async function fetchJSON(url, retries = CONFIG.MAX_RETRIES) {
  let lastErr;
  for (let i = 1; i <= retries; i++) {
    try {
      const req = new Request(url);
      req.timeoutInterval = CONFIG.TIMEOUT_SECONDS;
      const data = await req.loadJSON();
      if (data.error) throw new Error(data.message || "API error");
      return data;
    } catch (e) {
      lastErr = e;
      console.log(`Attempt ${i}/${retries}: ${e.message}`);
      if (i < retries) {
        notify("⏳ Retrying...", `Attempt ${i} failed. Waiting...`);
        await new Promise(r => Timer.schedule(CONFIG.RETRY_DELAY_MS, false, r));
      }
    }
  }
  throw lastErr;
}

function openVLC(url) {
  Safari.open(`vlc://${encodeURIComponent(url)}`);
}

// ─── MAIN ───────────────────────────────────────────────────

async function main() {
  let input = args.shortcutParameter;

  // If run directly in Scriptable, show prompt
  if (!input) {
    const p = new Alert();
    p.title = "🏴‍☠️ One Piece";
    p.message = "Enter the episode number:";
    p.addTextField("Episode #", "1");
    p.addAction("▶ Play");
    p.addCancelAction("Cancel");
    if (await p.presentAlert() === -1) { Script.complete(); return; }
    input = p.textFieldValue(0);
  }

  const epNum = parseInt(input, 10);
  if (isNaN(epNum) || epNum < 1) {
    await showAlert("❌ Invalid", `"${input}" is not a valid episode number.`);
    Script.complete();
    return;
  }

  console.log(`🎬 One Piece Episode ${epNum}`);
  notify("🏴‍☠️ One Piece", `Loading Episode ${epNum}...`);

  // Fetch stream from API
  const url = `${CONFIG.API_BASE}/api/stream/${CONFIG.ANIME_ID}/${epNum}`;
  console.log(`📡 ${url}`);

  let data;
  try {
    data = await fetchJSON(url);
  } catch (e) {
    await showAlert("❌ API Error", `${e.message}\n\nAPI: ${CONFIG.API_BASE}`);
    Script.complete();
    return;
  }

  if (!data.m3u8) {
    await showAlert("❌ No Stream", `No m3u8 found for Episode ${epNum}.`);
    Script.complete();
    return;
  }

  console.log(`🎯 m3u8: ${data.m3u8}`);

  // Build proxied m3u8 URL so VLC gets correct headers
  const referer = data.referer || "";
  const proxyUrl = `${CONFIG.API_BASE}/api/proxy/m3u8?url=${encodeURIComponent(data.m3u8)}&referer=${encodeURIComponent(referer)}`;
  console.log(`🔄 Proxy: ${proxyUrl}`);

  notify("🎬 Opening Safari", `Episode ${epNum} • 1080p`);

  // Pass the proxy URL back to Apple Shortcuts
  Script.setShortcutOutput(proxyUrl);

  // If run directly in the Scriptable app, just open it in Safari
  if (config.runsInApp) {
    Safari.open(proxyUrl);
  }

  console.log("✅ Sent link to Shortcuts / Safari");
  Script.complete();
}

await main();
