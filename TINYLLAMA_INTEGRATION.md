# TinyLlama Integration Guide for Fonte Android

This guide walks through integrating TinyLlama 1.1B into the Fonte Android app.

## What is TinyLlama?

TinyLlama is a 1.1B parameter language model:
- **Parameters**: 1.1 billion
- **Size (quantized)**: ~600-700 MB
- **Performance**: Fast inference on mobile devices
- **Quality**: Surprisingly good for such a small model
- **License**: Apache 2.0

## Prerequisites

- Windows, Mac, or Linux system with internet access
- Python 3.8+ installed
- ~2-3 GB free disk space (for download and conversion)
- Git (optional, for cloning llama.cpp)

## Step 1: Download TinyLlama GGML Model

### Option A: Using Python (Recommended)

Save this script as `download_tinyllama.py`:

```python
#!/usr/bin/env python3
"""Download TinyLlama GGML quantized model from Hugging Face"""

import os
import sys
from pathlib import Path

def download_with_curl(url, output_path):
    """Download file using curl"""
    import subprocess
    cmd = ['curl', '-L', '-o', output_path, url]
    print(f"Downloading with curl...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    return True

def download_with_urllib(url, output_path):
    """Download file using urllib"""
    import urllib.request
    print(f"Downloading TinyLlama GGML model...")
    print(f"URL: {url}")
    print(f"Output: {output_path}")
    
    try:
        urllib.request.urlretrieve(url, output_path, reporthook=progress_hook)
        print(f"\n✓ Download complete: {output_path}")
        size_mb = os.path.getsize(output_path) / (1024*1024)
        print(f"  Size: {size_mb:.2f} MB")
        return True
    except Exception as e:
        print(f"✗ Download failed: {e}")
        return False

def progress_hook(block_num, block_size, total_size):
    """Progress indicator for downloads"""
    downloaded = block_num * block_size
    if total_size > 0:
        percent = min(downloaded * 100 / total_size, 100)
        print(f"\rProgress: {percent:.1f}% ({downloaded / (1024*1024):.1f} MB)", end='')

def main():
    # Model URL - Q4_K_M quantization (good balance of size/quality)
    url = "https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGML/resolve/main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf?download=true"
    
    # Output path
    output_path = "tinyllama-1.1b-q4_k_m.gguf"
    
    if os.path.exists(output_path):
        size_mb = os.path.getsize(output_path) / (1024*1024)
        print(f"✓ Model already exists: {output_path}")
        print(f"  Size: {size_mb:.2f} MB")
        return 0
    
    print("=" * 60)
    print("TinyLlama GGML Model Download")
    print("=" * 60)
    print(f"Model: TinyLlama 1.1B Chat v1.0 (Q4_K_M quantized)")
    print(f"Size: ~600-700 MB")
    print(f"Source: Hugging Face")
    print("=" * 60)
    print()
    
    # Try download
    try:
        if not download_with_urllib(url, output_path):
            print("\nTrying with curl...")
            if not download_with_curl(url, output_path):
                print("\n✗ Download failed with both methods")
                return 1
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

Run it:
```bash
python download_tinyllama.py
```

### Option B: Manual Download

1. Visit: https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGML
2. Download: `tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf` (~690 MB)
3. Save to your working directory

## Step 2: Convert GGML to TensorFlow Lite

Unfortunately, direct GGML → TFLite conversion is complex. We have two options:

### Option A: Use Pre-Converted TFLite (If Available)

Check if a pre-converted version exists:
- Hugging Face (search "TinyLlama TFLite")
- Or convert manually using Option B

### Option B: Convert Using ONNX Intermediate

This is the recommended path:

1. **Install dependencies**:
```bash
pip install onnx onnxruntime tensorflow tf-tflite-onnx-converter
pip install numpy scipy
```

2. **Use llama.cpp for conversion**:
```bash
# Clone llama.cpp
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp

# Build
mkdir build && cd build
cmake ..
cmake --build . --config Release

# Convert GGML to ONNX (if supported)
python ../convert.py ../tinyllama-1.1b-q4_k_m.gguf --outfile tinyllama.onnx

# Then convert ONNX to TFLite using converter
```

### Option C: Use Simplified Approach for Testing

For now, we'll use a placeholder approach that demonstrates the integration:

**Create a test TFLite stub** - Save as `create_test_model.py`:

```python
#!/usr/bin/env python3
"""Create a test TFLite model for Fonte (not real LLM)"""

import struct
import os

def create_minimal_tflite():
    """Create a minimal valid TFLite model file"""
    # This creates a valid but non-functional TFLite file
    # Just for testing the app infrastructure
    
    tflite_data = b'\x54\x46\x4c\x33'  # TFLite magic number
    tflite_data += b'\x00' * 100  # Padding (simplified)
    
    output_path = "model.tflite"
    with open(output_path, 'wb') as f:
        f.write(tflite_data)
    
    print(f"✓ Test TFLite model created: {output_path}")
    return output_path

if __name__ == "__main__":
    create_minimal_tflite()
    print("\nNOTE: This is a stub for testing only!")
    print("For real LLM inference, use actual TinyLlama TFLite conversion")
```

## Step 3: Place Model in Android Assets

Once you have the `.tflite` file:

1. **Create the models directory**:
```bash
mkdir -p fonte\android\app\src\main\assets\models
```

2. **Copy the model**:
```bash
copy model.tflite fonte\android\app\src\main\assets\models\model.tflite
```

3. **Verify**:
```bash
dir fonte\android\app\src\main\assets\models\model.tflite
```

Expected output:
```
02/02/2025  03:45 PM        690,000,000 model.tflite
```

## Step 4: Update SimpleLLMEngine (Optional)

The existing `SimpleLLMEngine.kt` already supports loading from assets. No code changes needed!

However, if you want to optimize for TinyLlama specifically:

**File: `app/src/main/kotlin/com/fonte/SimpleLLMEngine.kt`**

Optional updates:
```kotlin
// Update constants for TinyLlama
companion object {
    private const val VOCAB_SIZE = 32000  // TinyLlama vocab
    private const val CONTEXT_LENGTH = 2048
    private const val MAX_TOKENS = 256  // Shorter for speed
    private const val BOS_TOKEN = 1
    private const val EOS_TOKEN = 2
}

// Update prompt building for TinyLlama chat format
private fun buildPromptForTinyLlama(message: String): String {
    return "<|im_start|>user\n$message<|im_end|>\n<|im_start|>assistant\n"
}
```

## Step 5: Build and Test

1. **Build the APK**:
```bash
cd fonte\android
gradlew.bat clean build -x test
```

2. **Deploy to emulator**:
```bash
adb install app\build\outputs\apk\debug\app-debug.apk
adb shell am start -n com.fonte/.MainActivity
```

3. **Test the chat**:
   - Open the app
   - Type: "Hello, what is TinyLlama?"
   - Should see LLM-generated response (if model loaded)
   - If model not loaded, will show mock response

## Troubleshooting

### "Model not found" error
→ Check file exists at: `app/src/main/assets/models/model.tflite`

### APK too large
→ TinyLlama model (~690 MB) is large
→ Solutions:
   - Use AAB (Android App Bundle) instead
   - Split APK by architecture
   - Or compress model in assets

### Model loads but inference is slow
→ Normal for 1.1B model on mobile
→ Expected: 200-500ms per token
→ Optimization: Use quantized version (Q4_K_M already is)

### Tokenization errors
→ TinyLlama uses specific tokenization
→ Update `SimpleTokenizer.kt` to use proper tokenizer
→ Consider using: https://github.com/openai/tiktoken

## Real TinyLlama Conversion (Advanced)

For a production implementation:

```bash
# Using llama.cpp
./llama-quantize tinyllama-1.1b-q4_k_m.gguf tinyllama-q4.tflite

# Or using custom converter
python convert_ggml_to_tflite.py \
  --input tinyllama-1.1b-q4_k_m.gguf \
  --output model.tflite \
  --quantization q4_k_m
```

## Performance Expectations

With TinyLlama 1.1B on a modern Android device:

| Metric | Value |
|--------|-------|
| Inference Time | 300-600ms per token |
| Memory Usage | 1.5-2.5 GB |
| Storage | ~690 MB model file |
| Battery Impact | Moderate (CPU-intensive) |
| Max Tokens | 256-512 (balanced) |
| Response Time (4 tokens) | ~1.2-2.4 seconds |

## Next Steps

1. **Download TinyLlama** using the script above
2. **Convert to TFLite** (or find pre-converted)
3. **Place in assets**: `app/src/main/assets/models/model.tflite`
4. **Rebuild**: `gradlew.bat clean build`
5. **Deploy and test**: Full LLM inference should work!

## Alternative Models

If TinyLlama doesn't work for your use case:

| Model | Size | Performance | Quantized |
|-------|------|-------------|-----------|
| TinyLlama 1.1B | 690 MB | Very Fast | Q4_K_M |
| Phi-2 2.7B | 1.6 GB | Fast | Q4_K_M |
| Mistral 7B | 4-5 GB | Slower | Q4_K_M |
| Llama-2 7B | 3.5-5 GB | Slower | Q4_K_M |

## Resources

- **TinyLlama**: https://github.com/jzhang38/TinyLlama
- **TheBloke GGML**: https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGML
- **llama.cpp**: https://github.com/ggerganov/llama.cpp
- **TensorFlow Lite**: https://www.tensorflow.org/lite
- **Hugging Face**: https://huggingface.co

## Questions?

Refer to:
- `BUILD_INSTRUCTIONS.md` - Build system help
- `IMPLEMENTATION_SUMMARY.md` - Architecture overview
- `SimpleLLMEngine.kt` - Model loading code
