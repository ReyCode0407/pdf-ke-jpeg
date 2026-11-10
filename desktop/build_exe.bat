@echo off
echo === Build PIXORA by Rey (.exe) ===
pip install customtkinter pymupdf pillow pdf2docx pyinstaller
pyinstaller --noconfirm --onefile --windowed --collect-all customtkinter --collect-all pdf2docx --collect-all docx --icon icon.ico --name PIXORA pixora.py
echo.
echo Selesai! File exe ada di folder: dist\PIXORA.exe
pause
