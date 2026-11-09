@echo off
echo === Build PDF to JPEG Studio (.exe) ===
pip install customtkinter pymupdf pillow pyinstaller
pyinstaller --noconfirm --onefile --windowed --collect-all customtkinter --name "PDF2JPEG-Studio" pdf_to_jpeg.py
echo.
echo Selesai! File exe ada di folder: dist\PDF2JPEG-Studio.exe
pause
