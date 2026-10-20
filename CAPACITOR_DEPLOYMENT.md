# Fonte Capacitor Mobile Deployment Guide

Complete guide for deploying Fonte to Android via Capacitor + Chaquopy.

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│              Android Device (APK)                    │
├─────────────────────────────────────────────────────┤
│  ┌──────────────────┐      ┌──────────────────┐    │
│  │   Web UI (HTML)  │      │   Python Backend │    │
│  │  • Capacitor     │◄────►│  • Flask API     │    │
│  │  • Vanilla JS    │      │  • LLM Models    │    │
│  │  • ~7KB total    │      │  • Knowledge DB  │    │
│  └──────────────────┘      └──────────────────┘    │
│         Port: 80                  Port: 5000       │
└─────────────────────────────────────────────────────┘
         ↑
         │ (Optional: Remote API)
         │
    Optional: Remote Server
    for distributed deployment
```

## Chaquopy Integration

Chaquopy allows embedding Python directly in Android APK.

### Step 1: Edit `android/app/build.gradle`

Add the Chaquopy plugin:

```gradle
plugins {
    id 'com.android.application'
    id 'com.chaquo.python'
}

android {
    compileSdk 33

    defaultConfig {
        applicationId "com.aethermark.fonte"
        minSdk 21
        targetSdk 33
        versionCode 1
        versionName "1.0.0"
    }
}

chaquopy {
    defaultTargetApi 24
    productFlavors {
        free {
            targetApi 26
        }
    }

    ndk {
        version "24.0.8215888"
    }

    python {
        version "3.9"

        staticBuild false

        pip {
            // Install Fonte dependencies
            install "-r", "../requirements-mobile.txt"
            
            // Additional libraries for mobile
            install "pyjnius"
        }
    }
}

dependencies {
    // Chaquopy
    implementation 'com.chaquo.python:python:3.9'
}
```

### Step 2: Create Chaquopy Bootstrap Service

Create `android/app/src/main/java/com/aethermark/fonte/FonteAPIService.java`:

```java
package com.aethermark.fonte;

import android.app.Service;
import android.content.Intent;
import android.os.IBinder;
import android.util.Log;
import com.chaquo.python.Python;
import com.chaquo.python.PyObject;

public class FonteAPIService extends Service {
    private static final String TAG = "FonteAPI";
    private Thread apiThread;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Log.d(TAG, "Starting Fonte API Service");

        // Start Flask API in background thread
        apiThread = new Thread(() -> {
            try {
                Python py = Python.getInstance();
                PyObject api_server = py.getModule("api_server");
                api_server.callAttr("run_server");
            } catch (Exception e) {
                Log.e(TAG, "Error running API server", e);
            }
        });
        apiThread.start();

        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        Log.d(TAG, "Stopping Fonte API Service");
        if (apiThread != null && apiThread.isAlive()) {
            apiThread.interrupt();
        }
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
```

### Step 3: Update `MainActivity.java`

```java
package com.aethermark.fonte;

import android.content.Intent;
import android.os.Build;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(android.os.Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Start Fonte API service
        Intent serviceIntent = new Intent(this, FonteAPIService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent);
        } else {
            startService(serviceIntent);
        }
    }
}
```

### Step 4: Update `AndroidManifest.xml`

Add service declaration:

```xml
<manifest>
    <application>
        <activity
            android:name=".MainActivity"
            android:label="@string/title_activity_main"
            android:theme="@style/AppTheme"
            android:launchMode="singleTask"
            android:configChanges="orientation|keyboardHidden|keyboard|screenSize|locale|smallestScreenSize|screenLayout|uiMode">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <!-- Fonte API Service -->
        <service
            android:name=".FonteAPIService"
            android:exported="false">
        </service>
    </application>

    <!-- Permissions -->
    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
</manifest>
```

## Building the APK

### 1. Sync Capacitor

```bash
cd capacitor-mobile
npx cap sync android
```

### 2. Build Android Project

```bash
cd android
./gradlew assembleDebug
```

**Output:** `app/build/outputs/apk/debug/app-debug.apk`

### 3. Deploy to Emulator

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

### 4. Launch App

```bash
adb shell am start -n com.aethermark.fonte/.MainActivity
```

### 5. View Logs

```bash
adb logcat -s "FonteAPI"
```

## Troubleshooting

### Python won't initialize
```bash
adb logcat | grep "chaquopy"
```

Check for missing native libraries or Python version issues.

### Flask API fails to start
```bash
adb shell
cd /data/local/tmp
python3 /path/to/api_server.py
```

### LLM models not found
Ensure models are copied to `/data/data/com.aethermark.fonte/files/models/`

### Port 5000 already in use
Change port in `api_server.py`:
```python
API_PORT = 5001
```

## Performance Optimization

### Reduce APK Size
- Remove unused models
- Use `--strip-libs` during build
- Minify JavaScript/CSS

### Speed Up Initialization
- Lazy-load models
- Cache LLM responses
- Use quantized models (int8)

### Memory Optimization
- Monitor with: `adb shell dumpsys meminfo`
- Reduce batch size
- Cleanup old conversations

## Release Build

### 1. Create Signing Key

```bash
keytool -genkey -v -keystore fonte-release.keystore \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias fonte-release
```

### 2. Configure Gradle

Create `android/app/keystore.gradle`:

```gradle
android {
    signingConfigs {
        release {
            storeFile file("../fonte-release.keystore")
            storePassword System.getenv("KEYSTORE_PASSWORD")
            keyAlias System.getenv("KEY_ALIAS")
            keyPassword System.getenv("KEY_PASSWORD")
        }
    }

    buildTypes {
        release {
            signingConfig signingConfigs.release
            minifyEnabled true
            shrinkResources true
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt')
        }
    }
}
```

### 3. Build Release APK

```bash
cd android
./gradlew assembleRelease
```

**Output:** `app/build/outputs/apk/release/app-release.apk`

## Monitoring

### Check API Status

```bash
curl http://127.0.0.1:5000/api/status
```

### Monitor Device Performance

```bash
adb shell top -n 5
```

### View Complete Logs

```bash
adb logcat > fonte-debug.log &
# Let it run for a while
# Ctrl+C to stop
cat fonte-debug.log | grep "Fonte\|Error\|Exception"
```

## Distribution

### Google Play
1. Sign release APK
2. Create Play Console account
3. Upload to Play Store

### Direct APK Distribution
```bash
adb push app/build/outputs/apk/release/app-release.apk /sdcard/
```

## Next Steps

1. Test on physical device
2. Optimize LLM model for mobile
3. Add offline support
4. Create iOS build via Xcode
