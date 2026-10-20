@echo off
REM Fonte + TinyLlama Integration Script
REM Downloads TinyLlama and integrates it into the Android app

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo  Fonte Android - TinyLlama Integration
echo ============================================================
echo.

REM Set paths
set PROJECT_DIR=%~dp0
set ANDROID_DIR=%PROJECT_DIR%android
set ASSETS_DIR=%ANDROID_DIR%\app\src\main\assets\models
set MODEL_URL=https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGML/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf?download=true
set TEMP_MODEL=%TEMP%\tinyllama-1.1b-q4_k_m.gguf
set FINAL_MODEL=%ASSETS_DIR%\model.gguf

echo Step 1: Creating assets directory...
if not exist "%ASSETS_DIR%" (
    mkdir "%ASSETS_DIR%"
    echo   [OK] Created: %ASSETS_DIR%
) else (
    echo   [OK] Directory exists: %ASSETS_DIR%
)

echo.
echo Step 2: Checking for existing model...
if exist "%FINAL_MODEL%" (
    for /F "tokens=*" %%A in ('powershell -Command "(Get-Item '%FINAL_MODEL%').Length / 1MB"') do set SIZE=%%A
    echo   [OK] Model already in place: %FINAL_MODEL%
    echo        Size: !SIZE! MB
    goto BUILD
)

echo.
echo Step 3: Downloading TinyLlama GGML model...
echo   This may take 10-20 minutes (~690 MB)
echo   URL: %MODEL_URL%
echo.

REM Try PowerShell download
powershell -Command "try { [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('%MODEL_URL%', '%TEMP_MODEL%'); Write-Host 'Download complete' } catch { exit 1 }"

if errorlevel 1 (
    echo.
    echo   [ERROR] PowerShell download failed
    echo.
    echo   Alternative: Download manually from:
    echo   %MODEL_URL%
    echo.
    echo   Save to: %TEMP_MODEL%
    echo   Then run this script again
    echo.
    pause
    exit /b 1
)

echo   [OK] Download complete

echo.
echo Step 4: Verifying model...
if not exist "%TEMP_MODEL%" (
    echo   [ERROR] Model file not found after download
    pause
    exit /b 1
)

for /F "tokens=*" %%A in ('powershell -Command "(Get-Item '%TEMP_MODEL%').Length / 1MB"') do set DL_SIZE=%%A
echo   [OK] File size: !DL_SIZE! MB

echo.
echo Step 5: Copying model to Android assets...
copy "%TEMP_MODEL%" "%FINAL_MODEL%"

if not exist "%FINAL_MODEL%" (
    echo   [ERROR] Failed to copy model
    pause
    exit /b 1
)

echo   [OK] Model copied to: %FINAL_MODEL%

:BUILD
echo.
echo ============================================================
echo Step 6: Building Android app with TinyLlama...
echo ============================================================
echo.

cd /d "%ANDROID_DIR%"

REM Check for gradlew
if not exist "gradlew.bat" (
    echo [ERROR] gradlew.bat not found in %ANDROID_DIR%
    pause
    exit /b 1
)

echo Building with Gradle...
call gradlew.bat clean build -x test

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo ============================================================
echo [SUCCESS] Build complete!
echo ============================================================
echo.
echo APK Location: %ANDROID_DIR%\app\build\outputs\apk\debug\app-debug.apk
echo.
echo Next steps:
echo   1. Connect Android device or emulator
echo   2. Run: adb install app\build\outputs\apk\debug\app-debug.apk
echo   3. Launch the app and test TinyLlama!
echo.
pause
