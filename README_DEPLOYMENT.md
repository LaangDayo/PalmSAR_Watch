# PalmSAR Watch — Online WebGIS

Paket ini berisi antarmuka Streamlit yang diperbarui untuk dashboard WebGIS PalmSAR Watch.
Pipeline NISAR yang sudah ada (`step1_search.py` sampai `step6_hls_count.py`) tidak diubah.

## 1. Struktur folder

Simpan hasil ekspor Step 3 di dalam folder proyek:

```text
PalmSAR-Watch/
├── app.py
├── requirements.txt
├── data/
│   └── sumut_main/
│       ├── stack.nc
│       └── meta.json
└── validation/
    └── sumut_main/
        └── accuracy_report.txt   # opsional, setelah validasi
```

`stack.nc` dan `meta.json` dibuat oleh `step3_change_export.py`.
Pastikan nama folder site sama dengan `SITE_ID` pada `config.py`.

## 2. Uji lokal

Di terminal pada folder proyek:

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Jika pipeline pemrosesan juga dijalankan pada komputer yang sama, tetap instal dependensi
pipeline dari daftar dependensi lengkap proyek. `requirements.txt` di paket ini hanya
memuat dependensi runtime dashboard.

## 3. Deploy online dengan Streamlit Community Cloud

1. Buat repository GitHub.
2. Masukkan `app.py`, `requirements.txt`, serta folder `data/<site_id>/` yang berisi
   `stack.nc` dan `meta.json`.
3. Pastikan `stack.nc` tidak melampaui batas ukuran file GitHub (file biasa dibatasi 100 MB).
4. Buka https://share.streamlit.io/ dan masuk dengan GitHub.
5. Pilih **Create app**, repository, branch, dan file utama `app.py`.
6. Deploy. Streamlit akan memasang paket dari `requirements.txt`.
7. Setelah deployment selesai, gunakan URL aplikasi yang diberikan Streamlit.

## 4. Jika stack.nc terlalu besar

Jangan memaksa mengunggah file NetCDF besar ke GitHub. Simpan data pada object storage
yang mendukung HTTPS (misalnya Cloudflare R2 atau Amazon S3), lalu ubah strategi pemuatan
data agar aplikasi mengambil file dari storage tersebut. Untuk tahap ini, diperlukan URL
akses data dan pengaturan autentikasi/akses publik yang aman. Jangan menaruh password,
Earthdata token, atau access key di source code maupun repository.

## 5. Catatan teknis

- Aplikasi membaca `data/<site_id>/stack.nc` dan `meta.json`.
- Layer yang tersedia: RVI, ΔRVI, change classes, dan HV backscatter.
- Peta menggunakan basemap Esri World Imagery atau OpenStreetMap.
- Grafik temporal menampilkan median RVI dan mean HV per tanggal.
- Laporan akurasi ditampilkan jika `validation/<site_id>/accuracy_report.txt` tersedia.
- Luas yang dihitung dari koordinat geografis merupakan estimasi. Untuk angka final,
  gunakan penghitungan luas pada CRS proyeksi yang sesuai.
- Jangan memasukkan kredensial Earthdata atau file rahasia ke repository publik.
