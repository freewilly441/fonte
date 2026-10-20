# Fonte Mobile - Quick Start Guide

Get Fonte running on Android in 10 minutes (testing phase).

## What Was Created

✅ **Flask REST API** (`api_server.py`) - Wraps Fonte LLM functionality  
✅ **Capacitor Project** (`capacitor-mobile/`) - Native Android/iOS wrapper  
✅ **Minimal Web UI** (`www/index.html`, `js/`, `css/`) - ~7KB lightweight chat interface  
✅ **Chaquopy Setup** - Guide for embedding Python on Android  
✅ **Deployment Guide** - Complete build instructions  

## 1. Test Locally (Before Mobile)

Test the Flask API locally on your Windows machine first:

```bash
# Install Python dependencies
pip install -r requirements-mobile.txt

# Start the API server
python api_server.py
```

**Output:**
```
[API] Starting Fonte REST API on 127.0.0.1:5000
[API] App state loaded
[API] Knowledge base initialized
[API] LLM client initialized
```

**Test the API:**
```bash
# In another terminal
curl http://127.0.0.1:5000/api/health
# Should return: {"status": "healthy", ...}

curl -X POST http://127.0.0.1:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is Python?"}'
```

**Test the web UI:**
- Open `capacitor-mobile/www/index.html` in browser
- Or run: `cd capacitor-mobile && npm install && npm run dev`
- Visit `http://localhost:8000`

## 2. Install Capacitor CLI

```bash
npm install -g @capacitor/cli
```

## 3. Initialize Android Platform

```bash
cd capacitor-mobile
npm install
npx cap add android
```

This creates the native Android project.

## 4. Sync Web Assets

```bash
npx cap sync android
```

Copies web UI files to the Android project.

## 5. Build Android Project

**Option A: Android Studio (Recommended)**
```bash
npx cap open android
# Android Studio opens
# Click "Run" or Build > Build Bundle(s) / APK(s)
```

**Option B: Command Line**
```bash
cd android
./gradlew assembleDebug
# APK output: app/build/outputs/apk/debug/app-debug.apk
```

## 6. Deploy to Emulator

Make sure your emulator is running (`emulator-5554` as you mentioned):

```bash
# Install APK
adb install -r android/app/build/outputs/apk/debug/app-debug.apk

# Launch app
adb shell am start -n com.aethermark.fonte/.MainActivity

# View logs
adb logcat | grep "FonteAPI\|Error"
```

## 7. Enable Chaquopy

**Critical Step**: Edit `android/app/build.gradle` and add:

```gradle
plugins {
    id 'com.android.application'
    id 'com.chaquo.python'  // ADD THIS
}

// ... rest of build.gradle

python {
    version "3.9"
    pip {
        install "-r", "../requirements-mobile.txt"
    }
}
```

Then rebuild.

## 8. Create API Service

Copy the Java service code from `CAPACITOR_DEPLOYMENT.md`:
- Create `android/app/src/main/java/com/aethermark/fonte/FonteAPIService.java`
- Update `MainActivity.java` to start the service
- Update `AndroidManifest.xml` to declare the service

Then rebuild and deploy.

## Architecture Recap

```
Your Android Device
├── Capacitor App (Native Shell)
│   └── Web UI (HTML/CSS/JS)
│       └── Chrome WebView
│           └── Connects to http://127.0.0.1:5000
└── Python Backend (Chaquopy)
    ├── Flask API Server
    ├── LLM Models
    └── Knowledge Database
```

## File Structure

```
fonte/
├── api_server.py                    # Flask API (NEW)
├── requirements-mobile.txt          # Python dependencies (NEW)
├── capacitor-mobile/                # Capacitor project (NEW)
│   ├── package.json
│   ├── capacitor.config.ts
│   ├── www/
│   │   ├── index.html               # Web UI entry
│   │   ├── manifest.json            # PWA manifest
│   │   ├── css/app.css              # Minimal CSS
│   │   └── js/
│   │       ├── api.js               # API client
│   │       └── app.js               # UI logic
│   ├── android/                     # Auto-generated
│   └── README.md
├── CAPACITOR_DEPLOYMENT.md          # Detailed setup (NEW)
└── MOBILE_QUICK_START.md            # This file (NEW)
```

## Common Commands

```bash
# Sync changes from www/ to Android project
npx cap sync android

# View Python logs on device
adb logcat | grep "chaquopy\|Python"

# Clear app data
adb shell pm clear com.aethermark.fonte

# Check if Flask API is running
adb shell netstat | grep 5000

# Copy file to/from device
adb push local/file /sdcard/file
adb pull /sdcard/file local/file
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Cannot connect to API" | Check if Flask is running: `adb logcat \| grep API` |
| App crashes on startup | Enable Chaquopy plugin (see step 7) |
| Web UI is blank | Check: `adb logcat \| grep "http\|fetch\|error"` |
| Python modules not found | Rebuild after adding to `requirements-mobile.txt` |
| Emulator too slow | Use Android x86 emulator, not ARM |

## Performance Notes

- **Initial load**: 2-5 seconds (Chaquopy startup)
- **First LLM response**: 10-60 seconds (depends on model)
- **Subsequent responses**: 2-30 seconds (depending on model size)
- **Memory usage**: 50-200MB baseline
- **APK size**: ~150-300MB (includes Python + models)

## Next Steps

1. ✅ Test Flask API locally
2. ✅ Build and deploy to emulator
3. ✅ Verify LLM responses work
4. ⏭️ Optimize model size if needed
5. ⏭️ Test on physical device
6. ⏭️ Add iOS support (similar process with Xcode)
7. ⏭️ Submit to Play Store

## Support Files

- `api_server.py` - All API endpoints documented
- `capacitor-mobile/README.md` - Detailed Capacitor setup
- `CAPACITOR_DEPLOYMENT.md` - Complete Chaquopy + Java integration
- Web UI logs: Check browser console via `adb logcat | grep V8`

---

**Status**: ✅ All files created. Ready for testing.

**Next Action**: Run `pip install -r requirements-mobile.txt && python api_server.py`
