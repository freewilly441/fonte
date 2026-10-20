# Fonte Mobile - Capacitor Wrapper

Lightweight native Android/iOS wrapper for Fonte LLM using Capacitor 5 + Chaquopy.

## Architecture

- **Backend**: Flask REST API (`api_server.py`) running via Chaquopy on Android
- **Frontend**: Minimal vanilla JavaScript web UI (~7KB total)
- **Transport**: HTTP/REST over localhost
- **Python**: Embedded via Chaquopy in the APK

## Setup

### Prerequisites
- Node.js 16+
- Android Studio (for Android development)
- Xcode (for iOS development)
- Java 11+

### Installation

```bash
cd capacitor-mobile
npm install
```

### Add Android Platform

```bash
npx cap add android
```

### Sync Web Assets

```bash
npx cap sync android
```

### Build & Deploy

#### Android

**Open in Android Studio:**
```bash
npx cap open android
```

**Build APK:**
```bash
cd android
./gradlew assembleDebug
```

**Deploy to emulator:**
```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.aethermark.fonte/.MainActivity
```

#### iOS

```bash
npx cap open ios
```

## Project Structure

```
capacitor-mobile/
├── www/                          # Web UI (static assets)
│   ├── index.html               # Main HTML
│   ├── manifest.json            # PWA manifest
│   ├── css/
│   │   └── app.css              # ~4KB minimal CSS
│   └── js/
│       ├── api.js               # ~2KB API client
│       └── app.js               # ~4KB UI logic
├── android/                      # Android native project (auto-generated)
├── package.json
├── capacitor.config.ts
└── README.md
```

## Chaquopy Configuration

The Android build requires Chaquopy to embed Python. Add to `android/app/build.gradle`:

```gradle
python {
    version "3.9"
    pip {
        install "-r", "requirements-mobile.txt"
    }
}
```

## API Endpoints

The Flask API exposes:

- `GET /api/health` - Health check
- `GET /api/status` - API/LLM status
- `POST /api/chat` - Send message, get LLM response
- `POST /api/search` - Search knowledge base
- `GET /api/config` - Get config
- `POST /api/config` - Update config

## Performance

- **Web UI**: ~7KB JavaScript + ~4KB CSS
- **Initial Load**: <2 seconds
- **Chat Response**: Depends on LLM model (1-30s typically)
- **Memory**: ~50-100MB (baseline)

## Development

### Hot Reload

```bash
npm run dev
```

Serves on `http://localhost:8000`

### Testing

Open browser dev tools and check:
- Console for errors
- Network tab for API calls
- Application tab for local storage

## Environment Variables

Set on device/Android environment:

```
FONTE_API_PORT=5000
FONTE_API_HOST=127.0.0.1
FONTE_DEBUG=1
```

## Troubleshooting

### "Cannot connect to API"
- Ensure Flask API is running
- Check `adb logcat` for Python errors
- Verify `127.0.0.1:5000` is accessible

### "LLM not initialized"
- Models may still be loading
- Check status via `GET /api/status`
- Allow 10-30s for first initialization

### Memory issues on device
- Reduce model size in config
- Close other apps
- Clear cache: `adb shell pm cache clear com.aethermark.fonte`

## Building for Release

### Android

```bash
cd android
./gradlew assembleRelease
# Sign APK with release keystore
```

### iOS

```bash
npx cap open ios
# In Xcode: Product > Build for Release
# Or use TestFlight/App Store
```

## License

Same as Fonte main project
