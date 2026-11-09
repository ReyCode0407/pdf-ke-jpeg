@echo off
echo === Build PIXORA by Rey (.exe) ===
pip install customtkinter pymupdf pillow pyinstaller
pyinstaller --noconfirm --onefile --windowed --collect-all customtkinter --icon icon.ico --name PIXORA pixora.py
echo.
echo Selesai! File exe ada di folder: dist\PIXORA.exe
pause
