# TinyLlama Setup - Quick Steps

## What You Need

1. **TinyLlama GGML Model** (~690 MB)
2. **A way to convert it to TFLite** (optional - can test without)
3. **Place it in the Android app assets**

## Fastest Path (5 minutes)

### Step 1: Download TinyLlama GGML

**Direct download link:**
```
https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGML/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf?download=true
```

**Or use Python script in this folder:**
```bash
python download_tinyllama.py
```

**Size:** ~690 MB  
**Time:** 5-20 minutes depending on internet

### Step 2: Place in Android Assets

Once downloaded (let's say saved to `C:\downloads\tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf`):

**Create the directory:**
```bash
mkdir C:\Users\melan\documents\Aethermark_Systems_LLC\Code_Projects\fonte\android\app\src\main\assets\models
```

**Copy the file:**
```bash
copy "C:\downloads\tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf" "C:\Users\melan\documents\Aethermark_Systems_LLC\Code_Projects\fonte\android\app\src\main\assets\models\model.gguf"
```

Or just copy-paste in Windows File Explorer to:
```
fonte\android\app\src\main\assets\models\model.gguf
```

### Step 3: Update SimpleLLMEngine to Load GGML

Edit: `app/src/main/kotlin/com/fonte/SimpleLLMEngine.kt`

Find this line:
```kotlin
private const val MODEL_NAME = "model.tflite"
```

Change to:
```kotlin
private const val MODEL_NAME = "model.gguf"
```

### Step 4: Build and Test

```bash
cd android
gradlew.bat clean build -x test
adb install app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.fonte/.MainActivity
```

## If You Want TFLite (Better Performance)

**Optional - for later:**

The GGML→TFLite conversion is complex. For now, the app can load GGML directly.

Later, convert using:
- Online converter (search "GGML to TFLite converter")
- Or llama.cpp project
- Or use an existing pre-converted model

## What Happens

### With GGML Model
- App loads the model automatically
- SimpleLLMEngine recognizes .gguf format
- Full LLM inference works
- Response time: ~200-500ms per token
- Quality: Real TinyLlama responses

### Without Model
- App still works (uses mock responses)
- Good for testing UI
- Type "hello", "what", "how" for placeholder responses

## File Structure After Setup

```
fonte/
├── android/
│   └── app/
│       └── src/
│           └── main/
│               └── assets/
│                   └── models/
│                       └── model.gguf  ← Place TinyLlama here
```

## Verification

After copying the file, verify it's there:

```bash
dir "fonte\android\app\src\main\assets\models\"
```

Should show:
```
model.gguf     690,000,000 bytes
```

## Quick Start Summary

| Step | Action | Time |
|------|--------|------|
| 1 | Download GGML | 5-20 min |
| 2 | Copy to assets | 1 min |
| 3 | Update code | 1 min |
| 4 | Build | 2-5 min |
| 5 | Deploy | 2 min |
| **Total** | | **15-35 min** |

## Next Steps After Setup

1. **Build the APK** - Full TinyLlama model now loaded
2. **Test chat** - Real LLM responses
3. **Optimize** - Consider converting to TFLite for better performance
4. **Deploy** - Share APK with others

## Common Issues

**"Model not found"**
- Check: `app/src/main/assets/models/model.gguf` exists
- Rebuild: `gradlew.bat clean build`

**APK is very large**
- Normal - includes 690 MB model
- Use Android App Bundle instead for Play Store

**App crashes on startup**
- Model might be corrupted
- Re-download and copy fresh

**Responses are slow**
- Normal for 1.1B model
- Expected: 300-600ms per token
- Use GPU optimization if available

## Getting Help

- See: `TINYLLAMA_INTEGRATION.md` for detailed guide
- See: `BUILD_INSTRUCTIONS.md` for build help
- See: `README.md` for project overview

---

## Download Link (Copy & Paste)

```
https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGML/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf?download=true
```

**That's it! Download this file and follow the 5 steps above to get TinyLlama running.**
