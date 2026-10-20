# Fonte Android Build Instructions

## Project Structure Completed

The following has been successfully set up:

### Configuration Files
- ✅ `build.gradle.kts` - App-level build configuration with all dependencies
- ✅ `build.gradle.kts` - Project-level build configuration
- ✅ `settings.gradle.kts` - Settings with proper repositories
- ✅ `gradle.properties` - Gradle memory and optimization settings
- ✅ `local.properties` - Android SDK path configuration
- ✅ `proguard-rules.pro` - ProGuard configuration for release builds
- ✅ `AndroidManifest.xml` - App manifest with permissions and activities

### UI Layer
- ✅ `activity_main.xml` - Main activity layout with Material Design 3
- ✅ `item_chat_message.xml` - Chat message bubble layout
- ✅ `colors.xml` - Material Design 3 color palette
- ✅ `strings.xml` - App strings and UI text
- ✅ `themes.xml` - Material Design 3 themes

### Kotlin Source Code
- ✅ `MainActivity.kt` - Main activity with ViewBinding and lifecycle
- ✅ `ChatViewModel.kt` - ViewModel with LiveData for message state
- ✅ `ChatAdapter.kt` - RecyclerView adapter for chat messages
- ✅ `ChatMessage.kt` - Data class for chat messages
- ✅ `SimpleLLMEngine.kt` - TensorFlow Lite inference engine
- ✅ `SimpleKnowledgeBase.kt` - SQLite semantic search knowledge base

### Build System
- ✅ Gradle 8.2.1 wrapper configured
- ✅ Android Gradle Plugin 8.2.0
- ✅ Kotlin plugin 1.9.21
- ✅ TensorFlow Lite dependencies

## Build Instructions

### Option 1: Using Gradle Wrapper (Recommended)

Open Command Prompt or PowerShell in the android directory:

```bash
cd C:\Users\melan\documents\Aethermark_Systems_LLC\Code_Projects\fonte\android

# Clean and build
gradlew.bat clean build -x test

# Or, build only the debug APK
gradlew.bat assembleDebug
```

The compiled APK will be at:
`app/build/outputs/apk/debug/app-debug.apk`

### Option 2: Using Android Studio

1. Open Android Studio
2. File → Open → Select the `fonte/android` directory
3. Gradle will sync automatically
4. Build → Make Project
5. Run → Run 'app'

### Option 3: Using Command Line with Cached Gradle

```bash
C:\Users\melan\.gradle\wrapper\dists\gradle-8.2.1-all\d8pvvlun5bx6sdtwqhf8y9z4b\gradle-8.2.1\bin\gradle.bat clean build -x test
```

## Deploy to Emulator

After building, deploy the APK to the running emulator:

```bash
# Check connected devices
adb devices

# Install the APK
adb install app/build/outputs/apk/debug/app-debug.apk

# Or, launch directly from Android Studio
gradlew.bat assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.fonte/.MainActivity
```

## Build Troubleshooting

### "SDK location not found"
Create or update `local.properties`:
```properties
sdk.dir=C:\Users\melan\AppData\Local\Android\sdk
```

### "Could not find gradle-wrapper.jar"
The wrapper JAR is cached in:
`C:\Users\melan\.gradle\wrapper\dists\gradle-8.2.1-all\...`

Or download manually:
```bash
gradle wrapper --gradle-version=8.2.1
```

### Gradle out of memory
Increase heap size in `gradle.properties`:
```properties
org.gradle.jvmargs=-Xmx2048m -Xms512m
```

## Next Steps

### 1. Integrate Real TensorFlow Lite Model
- Download a quantized 3-7B parameter model (TinyLlama, Phi-2, or similar)
- Convert GGML format to TFLite using conversion tools
- Place in `app/src/main/assets/models/model.tflite`
- Update `SimpleLLMEngine.kt` to load the actual model

### 2. Replace Placeholder Components
- **SimpleTokenizer**: Replace hash-based with proper BPE tokenizer
- **SimpleEmbeddingModel**: Use real TFLite embedding model instead of hash-based

### 3. Test on Emulator or Device
```bash
adb shell am start -n com.fonte/.MainActivity
```

### 4. Build Release APK
```bash
gradlew.bat assembleRelease
# Requires keystore configuration
```

## Project Architecture

```
fonte/android/
├── app/
│   ├── src/main/
│   │   ├── kotlin/com/fonte/
│   │   │   ├── MainActivity.kt
│   │   │   ├── ChatViewModel.kt
│   │   │   ├── ChatAdapter.kt
│   │   │   ├── ChatMessage.kt
│   │   │   ├── SimpleLLMEngine.kt
│   │   │   └── SimpleKnowledgeBase.kt
│   │   ├── res/
│   │   │   ├── layout/
│   │   │   │   ├── activity_main.xml
│   │   │   │   └── item_chat_message.xml
│   │   │   └── values/
│   │   │       ├── colors.xml
│   │   │       ├── strings.xml
│   │   │       └── themes.xml
│   │   ├── assets/models/
│   │   │   └── model.tflite (to be added)
│   │   └── AndroidManifest.xml
│   ├── build.gradle.kts
│   └── proguard-rules.pro
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties
├── local.properties
└── gradle/wrapper/
    └── gradle-wrapper.properties
```

## Tech Stack

- **Language**: Kotlin 1.9.21
- **Android API**: 26+ (minSdk)
- **UI Framework**: Material Design 3
- **Database**: SQLite (Room-compatible)
- **ML Framework**: TensorFlow Lite 2.13.0
- **Architecture**: MVVM with LiveData
- **Build System**: Gradle 8.2.1 with Kotlin DSL
- **Async**: Coroutines with Dispatchers

## Key Features

✅ Native Material Design 3 UI
✅ TensorFlow Lite inference pipeline
✅ SQLite semantic search knowledge base
✅ Cosine similarity embeddings
✅ Token generation with EOS detection
✅ Context window management (max 2048 tokens)
✅ Graceful degradation (works without model)
✅ Sample documents for testing

## Dependencies

- androidx.appcompat:appcompat:1.6.1
- androidx.core:core-ktx:1.10.1
- androidx.activity:activity-ktx:1.7.2
- androidx.fragment:fragment-ktx:1.6.1
- com.google.android.material:material:1.9.0
- androidx.lifecycle:lifecycle-viewmodel-ktx:2.6.1
- androidx.lifecycle:lifecycle-livedata-ktx:2.6.1
- androidx.lifecycle:lifecycle-runtime-ktx:2.6.1
- androidx.recyclerview:recyclerview:1.3.1
- androidx.room:room-runtime:2.5.2
- androidx.sqlite:sqlite:2.3.1
- org.tensorflow:tensorflow-lite:2.13.0
- org.tensorflow:tensorflow-lite-gpu:2.13.0
- org.tensorflow:tensorflow-lite-support:0.4.4
- org.jetbrains.kotlinx:kotlinx-coroutines-core:1.7.2
- org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.2
