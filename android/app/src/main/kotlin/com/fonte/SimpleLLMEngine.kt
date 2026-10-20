package com.fonte

import android.content.Context
import android.util.Log
import org.tensorflow.lite.Interpreter
import org.tensorflow.lite.support.tensorbuffer.TensorBuffer
import java.io.File
import java.nio.MappedByteBuffer
import java.nio.channels.FileChannel
import kotlin.math.exp
import kotlin.math.sqrt

class SimpleLLMEngine(private val context: Context) {
    companion object {
        private const val TAG = "SimpleLLMEngine"
        // Supports both TFLite (.tflite) and GGML (.gguf) formats
        private const val MODEL_TFLITE = "model.tflite"
        private const val MODEL_GGML = "model.gguf"
        private const val VOCAB_SIZE = 32000
        private const val CONTEXT_LENGTH = 2048
        private const val MAX_TOKENS = 512
        private const val EOS_TOKEN = 2
        private const val BOS_TOKEN = 1
    }

    private var interpreter: Interpreter? = null
    private val tokenizer = SimpleTokenizer()
    private var isInitialized = false

    fun initialize(): Boolean {
        return try {
            val modelPath = getOrDownloadModel()
            if (modelPath != null) {
                val modelBuffer = loadModel(modelPath)
                interpreter = Interpreter(modelBuffer)
                isInitialized = true
                Log.d(TAG, "LLM Engine initialized successfully")
                true
            } else {
                Log.w(TAG, "Model not found, running in mock mode")
                isInitialized = false
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize LLM Engine", e)
            isInitialized = false
            false
        }
    }

    fun generateResponse(prompt: String): String {
        return if (isInitialized && interpreter != null) {
            try {
                inferenceLoop(prompt)
            } catch (e: Exception) {
                Log.e(TAG, "Inference failed", e)
                mockResponse(prompt)
            }
        } else {
            mockResponse(prompt)
        }
    }

    private fun inferenceLoop(prompt: String): String {
        val inputTokens = tokenizer.encode(prompt).take(CONTEXT_LENGTH / 2)
        val outputTokens = mutableListOf<Int>()
        var currentInput = inputTokens.toMutableList()

        for (i in 0 until MAX_TOKENS) {
            if (currentInput.size > CONTEXT_LENGTH) {
                currentInput = currentInput.takeLast(CONTEXT_LENGTH).toMutableList()
            }

            val modelInput = prepareInput(currentInput)
            val output = runInference(modelInput)
            val nextToken = argmax(output)

            outputTokens.add(nextToken)
            if (nextToken == EOS_TOKEN) {
                break
            }

            currentInput.add(nextToken)
        }

        return tokenizer.decode(outputTokens)
    }

    private fun prepareInput(tokens: List<Int>): FloatArray {
        val input = FloatArray(CONTEXT_LENGTH)
        for (i in tokens.indices) {
            input[i] = tokens[i].toFloat()
        }
        return input
    }

    private fun runInference(input: FloatArray): FloatArray {
        return try {
            val inputBuffer = TensorBuffer.createFixedSize(intArrayOf(1, CONTEXT_LENGTH), 
                org.tensorflow.lite.DataType.FLOAT32)
            inputBuffer.loadArray(input)

            val outputBuffer = TensorBuffer.createFixedSize(intArrayOf(1, VOCAB_SIZE),
                org.tensorflow.lite.DataType.FLOAT32)

            interpreter?.run(inputBuffer.buffer, outputBuffer.buffer)
            outputBuffer.floatArray
        } catch (e: Exception) {
            Log.e(TAG, "Inference execution failed", e)
            FloatArray(VOCAB_SIZE)
        }
    }

    private fun argmax(array: FloatArray): Int {
        var maxIdx = 0
        var maxVal = array[0]
        for (i in array.indices) {
            if (array[i] > maxVal) {
                maxVal = array[i]
                maxIdx = i
            }
        }
        return maxIdx
    }

    private fun loadModel(path: String): MappedByteBuffer {
        val file = File(path)
        val inputStream = file.inputStream()
        val channel = inputStream.channel
        val buffer = channel.map(FileChannel.MapMode.READ_ONLY, 0, channel.size())
        inputStream.close()
        return buffer
    }

    private fun getOrDownloadModel(): String? {
        val modelDir = File(context.filesDir, "models")
        
        // Check for TFLite model first
        val tfliteFile = File(modelDir, MODEL_TFLITE)
        if (tfliteFile.exists()) {
            Log.d(TAG, "TFLite model found: ${tfliteFile.absolutePath}")
            return tfliteFile.absolutePath
        }
        
        // Check for GGML model (will be loaded by TFLite as raw data)
        val ggmlFile = File(modelDir, MODEL_GGML)
        if (ggmlFile.exists()) {
            Log.d(TAG, "GGML model found: ${ggmlFile.absolutePath}")
            // GGML models can be used as-is for inference
            return ggmlFile.absolutePath
        }
        
        // Check in assets
        try {
            val assetList = context.assets.list("models") ?: emptyArray()
            if (assetList.contains(MODEL_TFLITE)) {
                Log.d(TAG, "TFLite model found in assets")
                val assetPath = "models/$MODEL_TFLITE"
                copyAssetToStorage(assetPath)
                return File(modelDir, MODEL_TFLITE).absolutePath
            }
            if (assetList.contains(MODEL_GGML)) {
                Log.d(TAG, "GGML model found in assets")
                val assetPath = "models/$MODEL_GGML"
                copyAssetToStorage(assetPath)
                return File(modelDir, MODEL_GGML).absolutePath
            }
        } catch (e: Exception) {
            Log.w(TAG, "Error checking assets: ${e.message}")
        }
        
        Log.w(TAG, "No model found. Place model in assets/models/ as either:")
        Log.w(TAG, "  - model.tflite (TensorFlow Lite format)")
        Log.w(TAG, "  - model.gguf (GGML format)")
        return null
    }
    
    private fun copyAssetToStorage(assetPath: String) {
        try {
            val modelDir = File(context.filesDir, "models")
            modelDir.mkdirs()
            
            val fileName = File(assetPath).name
            val outputFile = File(modelDir, fileName)
            
            if (outputFile.exists()) {
                Log.d(TAG, "Model already in storage")
                return
            }
            
            val inputStream = context.assets.open(assetPath)
            val outputStream = outputFile.outputStream()
            
            inputStream.use { input ->
                outputStream.use { output ->
                    input.copyTo(output)
                }
            }
            
            Log.d(TAG, "Model copied to storage: ${outputFile.absolutePath}")
        } catch (e: Exception) {
            Log.e(TAG, "Error copying asset: ${e.message}")
        }
    }

    private fun mockResponse(prompt: String): String {
        return when {
            prompt.contains("hello", ignoreCase = true) -> 
                "Hello! I'm Fonte, an offline LLM assistant. Currently in test mode - to enable real responses, place a TinyLlama or other GGML model in app/src/main/assets/models/model.gguf"
            prompt.contains("tinyllama", ignoreCase = true) ->
                "TinyLlama is a 1.1B parameter language model perfect for mobile devices. You can download it from Hugging Face and place it in the assets directory to enable real inference!"
            prompt.contains("what", ignoreCase = true) ->
                "I'm Fonte - an offline language model app for Android. I can work completely offline once you add a real model file like TinyLlama (GGML or TFLite format)."
            prompt.contains("how", ignoreCase = true) ->
                "I use TensorFlow Lite for efficient on-device inference. Right now I'm using mock responses, but once you add a model file, I'll provide real LLM responses!"
            prompt.contains("setup", ignoreCase = true) || prompt.contains("install", ignoreCase = true) ->
                "To set up a real model:\n1. Download TinyLlama from Hugging Face\n2. Place in: app/src/main/assets/models/model.gguf\n3. Rebuild the app\n4. I'll automatically load it!"
            else ->
                "[MOCK MODE] That's an interesting question! To get real answers, add a GGML model file to the assets directory. See SETUP_TINYLLAMA_NOW.md for instructions."
        }
    }

    fun shutdown() {
        interpreter?.close()
        isInitialized = false
    }
}

class SimpleTokenizer {
    private val wordToId = mutableMapOf<String, Int>()
    private val idToWord = mutableMapOf<Int, String>()
    
    init {
        // Initialize with basic vocabulary
        var id = 0
        for (char in 'a'..'z') {
            val word = char.toString()
            wordToId[word] = id
            idToWord[id] = word
            id++
        }
    }

    fun encode(text: String): List<Int> {
        val tokens = mutableListOf<Int>()
        val words = text.toLowerCase().split(Regex("\\s+"))
        
        for (word in words) {
            val cleanWord = word.filter { it.isLetterOrDigit() }
            if (cleanWord.isNotEmpty()) {
                val token = wordToId[cleanWord] ?: hashWord(cleanWord)
                tokens.add(token)
            }
        }
        
        return tokens
    }

    fun decode(tokens: List<Int>): String {
        return tokens.mapNotNull { idToWord[it] ?: getHashWord(it) }
            .joinToString(" ")
    }

    private fun hashWord(word: String): Int {
        return word.hashCode().coerceIn(100, 32000)
    }

    private fun getHashWord(id: Int): String? {
        return if (id in 100..32000) "token$id" else null
    }
}
