@echo off
title Push SINBHA to GitHub
echo ========================================================
echo 🌸 Pushing SINBHA to GitHub: https://github.com/kbtteja456-KBT/SINBHA.git
echo ========================================================
echo.
"%LOCALAPPDATA%\Programs\Git\cmd\git.exe" push -u origin main
echo.
if %ERRORLEVEL% EQU 0 (
    echo ✅ Successfully pushed all code to GitHub!
    echo 👉 Next step: Open Render dashboard and deploy!
) else (
    echo ❌ Push failed. If prompted for GitHub login, please sign in via your browser.
)
echo.
pause
