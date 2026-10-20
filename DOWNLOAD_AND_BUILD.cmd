@echo off
REM Fonte + TinyLlama - Complete Build Script
REM This script downloads TinyLlama and integrates it into the Android app

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo  Fonte Android + TinyLlama - Download and Build
echo ============================================================
echo.

set PROJECT_DIR=%cd%
set ANDROID_DIR=%PROJECT_DIR%\android
set ASSETS_DIR=%ANDROID_DIR%\app\src\main\assets\models

REM Create assets directory
echo Step 1: Creating assets directory...
if not exist "%ASSETS_DIR%" mkdir "%ASSETS_DIR%"
echo   [OK] %ASSETS_DIR%
echo.

REM Check for existing model
if exist "%ASSETS_DIR%\model.gguf" (
    echo Step 2: Model already exists!
    for /F "tokens=*" %%A in ('powershell -Command "(Get-Item '%ASSETS_DIR%\model.gguf').Length / 1MB"') do set SIZE=%%A
    echo   [OK] Size: !SIZE! MB
    echo.
    goto BUILD
)

REM Download TinyLlama
echo Step 2: Downloading TinyLlama GGML Model
echo         File: tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
echo         Size: ~690 MB
echo         Time: 10-20 minutes depending on internet speed
echo.
echo   NOTE: HuggingFace downloads require browser. Please:
echo.
echo   1. Open this link in your browser:
echo      https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGML/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf?download=true
echo.
echo   2. Save the file to: %ASSETS_DIR%
echo      File should be named: model.gguf
echo.
echo   3. Run this script again
echo.

REM Open browser
start https://huggingface.io/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGML

:WAITFOR_MODEL
echo Waiting for model file (checking every 10 seconds)...
timeout /t 10

if exist "%ASSETS_DIR%\model.gguf" (
    for /F "tokens=*" %%A in ('powershell -Command "(Get-Item '%ASSETS_DIR%\model.gguf').Length / 1MB"') do set SIZE=%%A
    
    REM Check if file is reasonable size (>500 MB)
    for /F "tokens=*" %%A in ('powershell -Command "[int]((Get-Item '%ASSETS_DIR%\model.gguf').Length / 1MB)"') do set SIZE_INT=%%A
    
    if !SIZE_INT! gtr 500 (
        echo.
        echo [OK] Model downloaded successfully: !SIZE! MB
        goto BUILD
    )
)

echo Not found or too small. Waiting...
goto WAITFOR_MODEL

:BUILD
echo.
echo ============================================================
echo Step 3: Building Android App
echo ============================================================
echo.

cd /d "%ANDROID_DIR%"

if not exist gradlew.bat (
    echo [ERROR] gradlew.bat not found
    exit /b 1
)

echo Building with Gradle (this may take 2-5 minutes)...
call gradlew.bat clean build -x test

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    cd /d "%PROJECT_DIR%"
    exit /b 1
)

echo.
echo ============================================================
echo [SUCCESS] Build Complete!
echo ============================================================
echo.
echo APK Location:
echo   %ANDROID_DIR%\app\build\outputs\apk\debug\app-debug.apk
echo.
echo Next Steps:
echo   1. Ensure Android emulator is running (or device connected)
echo   2. Run: adb install app\build\outputs\apk\debug\app-debug.apk
echo   3. Run: adb shell am start -n com.fonte/.MainActivity
echo   4. Test chat with TinyLlama!
echo.

cd /d "%PROJECT_DIR%"

pause
