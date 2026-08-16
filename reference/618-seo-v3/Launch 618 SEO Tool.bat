@echo off
title 618 Media SEO Tool v3
cd /d "%~dp0"
echo.
echo  ==========================================
echo   618 Media SEO Tool v3
echo   Starting server...
echo   Open browser at: http://localhost:5618
echo  ==========================================
echo.
python app.py
echo.
echo  Server stopped. Press any key to close.
pause > nul
