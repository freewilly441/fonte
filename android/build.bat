@echo off
setlocal enabledelayedexpansion

REM Set gradle home
set GRADLE_HOME=C:\Users\melan\.gradle\wrapper\dists\gradle-8.2.1-all\d8pvvlun5bx6sdtwqhf8y9z4b\gradle-8.2.1

REM Run gradle build
"%GRADLE_HOME%\bin\gradle.bat" clean build -x test

pause
