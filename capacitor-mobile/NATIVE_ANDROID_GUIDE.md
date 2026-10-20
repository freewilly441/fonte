# Fonte Native Android App - Architecture & Build Guide

## Overview

We're rebuilding Fonte as a **pure native Android app** in Kotlin with zero external dependencies. This ensures a fully self-contained, offline-capable app.

## Architecture

### Stack
- **Language**: Kotlin 1.9.21
- **UI Framework**: Material Design 3 with Jetpack Compose
- **Database**: SQLite (with Room for type-safe queries)
- **LLM Inference**: TensorFlow Lite (ONNX Runtime for model execution)
- **Build Tool**: Gradle 8.2.0

### Project Structure

```
app/src/main/
├── java/com/aethermark/fonte/
│   ├── MainActivity.kt                 # Main chat activity
│   └── chat/
│       ├── ChatMessage.kt              # Data model for messages
│       ├── ChatViewModel.kt            # ViewModel for chat logic & state
│       ├── ChatAdapter.kt              # RecyclerView adapter for messages
│       ├── SimpleLLMEngine.kt          # LLM inference engine (TFLite)
│       └── SimpleKnowledgeBase.kt      # SQLite-based document store
├── res/
│   ├── layout/
│   │   ├── activity_main.xml           # Main chat UI layout
│   │   └── item_chat_message.xml       # Message item layout
│   ├── values/
│   │   ├── colors.xml                  # Material Design 3 colors
│   │   ├── themes.xml                  # App theme definition
│   │   └── strings.xml                 # String resources
│   └── mipmap/                         # App icons
└── AndroidManifest.xml                 # App configuration
```

## Current Status

### ✅ Completed
1. Material Design 3 UI layout (chat interface)
2. MVVM architecture with ViewModel
3. RecyclerView-based chat message display
4. Basic chat data models
5. Gradle configuration with necessary dependencies
6. SQLite database setup for knowledge base
7. Placeholder LLM and KB engines

### 🔄 In Progress
- **Gradle Build**: First build is downloading ~500MB of dependencies (TensorFlow Lite, Room, etc.)
- **View Binding**: Need to auto-generate binding classes (`ActivityMainBinding`)

### ⏳ Next Steps

#### 1. **Complete First Build**
```bash
cd android
./gradlew assembleDebug
# This will take 10-20 minutes on first run due to dependency download
```

#### 2. **Integrate TensorFlow Lite LLM**
File: `SimpleLLMEngine.kt`
- Load quantized GGML model (.tflite format)
- Implement tokenization/detokenization
- Execute inference on background thread using TFLite Interpreter
- Return generated text

```kotlin
// Pseudo-code for TFLite integration
private lateinit var interpreter: Interpreter

fun loadModel(modelPath: String) {
    val model = MappedByteBuffer.load(modelPath)
    interpreter = Interpreter(model)
}

fun generateResponse(prompt: String): String {
    val inputTokens = tokenize(prompt)
    val outputTokens = IntArray(1024) // Max output tokens
    interpreter.run(inputTokens, outputTokens)
    return detokenize(outputTokens)
}
```

#### 3. **Implement SQLite Knowledge Base**
File: `SimpleKnowledgeBase.kt`
- Add documents with embeddings
- Implement semantic search using cosine similarity
- Generate embeddings using TensorFlow Lite
- Return top-K most relevant documents for context injection

```kotlin
fun search(query: String): List<String> {
    val queryEmbedding = generateEmbedding(query)
    val results = findMostSimilar(queryEmbedding, topK = 5)
    return results.map { it.text }
}
```

#### 4. **Wire Up Chat Processing Pipeline**
File: `ChatViewModel.kt` - `processUserMessage()` method

Flow:
```
User Input
  ↓
Search Knowledge Base (get context documents)
  ↓
Build Prompt (inject context + question)
  ↓
Run LLM Inference (generate response)
  ↓
Display Response
```

#### 5. **Package a Model**
- Download or convert a small quantized LLM (3-7B parameters)
- Convert to ONNX or TFLite format
- Place in `app/src/main/assets/models/`
- Load on app startup

**Recommended Models**:
- `llama-2-7b-chat.ggml.q4_K_M.bin` (~3.8GB - too large)
- `tinyllama-1.1b` (~650MB - good for testing)
- `mistral-7b-q4` (~3.8GB - good quality)
- `phi-2` (~1.4GB - efficient)

#### 6. **Deploy to Emulator**
```bash
./gradlew installDebug
adb shell am start -n com.aethermark.fonte/.MainActivity
```

## Dependencies

Key libraries added:
```gradle
// UI
androidx.appcompat:appcompat:1.6.1
com.google.android.material:material:1.11.0

// Lifecycle & MVVM
androidx.lifecycle:lifecycle-viewmodel-ktx:2.7.0
androidx.activity:activity-ktx:1.8.1

// Database
androidx.room:room-runtime:2.6.1

// TensorFlow Lite
org.tensorflow:tensorflow-lite:2.14.0
org.tensorflow:tensorflow-lite-gpu:2.14.0

// Coroutines
org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3
```

## Known Issues & Fixes

### Issue: View Binding Not Generated
**Solution**: Ensure `buildFeatures { viewBinding true }` is in `app/build.gradle` ✅ (already added)

### Issue: Model File Too Large for APK
**Solution**: Download model on first run from assets or network
```kotlin
// Download model lazily on first use
fun ensureModelLoaded() {
    if (!modelFile.exists()) {
        downloadModel("https://...")
    }
}
```

### Issue: TensorFlow Lite OOM on Low-End Devices
**Solution**: Use quantized models (INT8, FP16) instead of FP32
- Reduces model size by 4-8x
- Slightly lower accuracy, still acceptable
- Much faster inference

## Performance Targets

- **App Size**: ~50-100MB (with small 1-2B model)
- **RAM Usage**: ~200-300MB at peak
- **Inference Speed**: 1-5 seconds per response (depends on model and input length)
- **First Response**: ~2-3 seconds (model loading + inference)
- **Subsequent**: ~1-2 seconds

## Testing Locally

### Build & Run
```bash
cd android
./gradlew installDebug
adb shell am start -n com.aethermark.fonte/.MainActivity
```

### View Logs
```bash
adb logcat | grep "ChatViewModel\|LLMEngine\|KnowledgeBase"
```

### Debug in Android Studio
1. Open project in Android Studio
2. Run > Run 'app'
3. Select emulator device
4. Wait for APK to build & install (~5 min first time)
5. Debug with breakpoints in Kotlin code

## Next Session

When returning to this project:
1. Check the Gradle build status
2. Fix any compilation errors
3. Integrate TensorFlow Lite model loading
4. Test basic chat flow without real LLM
5. Add actual model and test end-to-end

## Files Modified

- ✅ `android/app/build.gradle` - Added Kotlin, Material, TFLite deps
- ✅ `android/app/src/main/AndroidManifest.xml` - Simplified to native app
- ✅ `android/app/src/main/java/com/aethermark/fonte/MainActivity.kt` - Material Design chat UI
- ✅ `android/app/src/main/res/layout/activity_main.xml` - Chat interface
- ✅ `android/app/src/main/res/layout/item_chat_message.xml` - Message bubbles
- ✅ `android/app/src/main/res/values/{colors,themes,strings}.xml` - Material Design resources

All created from scratch - fully custom native Android implementation. 🚀
