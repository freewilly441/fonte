@echo off
REM Fonte Android - Quick Build Script
REM This script builds and deploys the app to an Android emulator

setlocal enabledelayedexpansion

echo.
echo ============================================
echo  Fonte Android Build & Deploy
echo ============================================
echo.

REM Check if gradle is available
where /Q gradlew.bat
if errorlevel 1 (
    echo Error: gradlew.bat not found. Please run from the android directory.
    pause
    exit /b 1
)

REM Check if adb is available
set ADB_PATH=C:\Users\melan\AppData\Local\Android\sdk\platform-tools\adb.exe
if not exist "%ADB_PATH%" (
    echo Error: Android SDK not found at expected location.
    echo Please ensure Android SDK is installed.
    pause
    exit /b 1
)

echo Step 1: Building APK...
call gradlew.bat clean assembleDebug -x test
if errorlevel 1 (
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo Step 2: Checking for connected devices...
"%ADB_PATH%" devices

echo.
echo Step 3: Installing APK...
set APK_PATH=app\build\outputs\apk\debug\app-debug.apk
if not exist "%APK_PATH%" (
    echo Error: APK not found at %APK_PATH%
    pause
    exit /b 1
)

"%ADB_PATH%" install -r "%APK_PATH%"
if errorlevel 1 (
    echo Installation failed!
    pause
    exit /b 1
)

echo.
echo Step 4: Launching app...
"%ADB_PATH%" shell am start -n com.fonte/.MainActivity

echo.
echo ============================================
echo  Build and deployment complete!
echo ============================================
echo.
pause
