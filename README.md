# PIXORA by Rey

Aplikasi pengolah PDF dan gambar.

- **PDF → Gambar:** ubah halaman PDF jadi JPEG, PNG, atau WebP. Pilih halaman, resolusi, dan kualitas.
- **Gambar → PDF:** gabungkan beberapa gambar jadi satu PDF dengan urutan yang bisa diatur.

Ada dua versi:

- **Web** (`web/index.html`): jalan di browser, file tidak diunggah ke server.
- **Desktop** (`desktop/pixora.py`): aplikasi Windows yang bisa dibuat jadi `PIXORA.exe`.

## Menjadikan web sendiri (GitHub Pages)

1. Upload seluruh isi folder ini ke repo GitHub, di branch `main`.
2. Buka **Settings > Pages**, pada **Source** pilih **GitHub Actions**.
3. Tunggu workflow **Deploy web** selesai di tab **Actions**.
4. Alamatnya: `https://<username>.github.io/<nama-repo>/`

## Membuat .exe tanpa Windows (GitHub Actions)

1. Buka tab **Actions > Build EXE > Run workflow**.
2. Setelah selesai, buka run-nya lalu unduh `PIXORA` dari bagian **Artifacts**. Isinya `PIXORA.exe`.
3. Untuk rilis tetap: buat tag, misalnya `git tag v1.0.0 && git push --tags`. File `.exe` akan terlampir di halaman **Releases**.

## Membuat .exe di komputer sendiri

Di Windows dengan Python 3.10+, jalankan `desktop/build_exe.bat`. Hasilnya ada di `desktop/dist/PIXORA.exe`.
