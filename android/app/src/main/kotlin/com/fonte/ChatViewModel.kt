package com.fonte

import android.content.Context
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.util.Date

class ChatViewModel : ViewModel() {
    private val _messages = MutableLiveData<List<ChatMessage>>(emptyList())
    val messages: LiveData<List<ChatMessage>> = _messages

    private val _isLoading = MutableLiveData<Boolean>(false)
    val isLoading: LiveData<Boolean> = _isLoading

    private val _isInitialized = MutableLiveData<Boolean>(false)
    val isInitialized: LiveData<Boolean> = _isInitialized

    private var llmEngine: SimpleLLMEngine? = null
    private var knowledgeBase: SimpleKnowledgeBase? = null

    fun initializeApp(context: Context) {
        viewModelScope.launch(Dispatchers.Default) {
            try {
                // Initialize LLM Engine
                llmEngine = SimpleLLMEngine(context)
                llmEngine?.initialize()

                // Initialize Knowledge Base
                knowledgeBase = SimpleKnowledgeBase(context)
                knowledgeBase?.initialize()

                // Add some sample documents
                addSampleDocuments()

                _isInitialized.postValue(true)
            } catch (e: Exception) {
                _isInitialized.postValue(false)
            }
        }
    }

    fun sendMessage(messageText: String) {
        val userMessage = ChatMessage(
            text = messageText,
            isUser = true
        )
        _messages.value = (_messages.value ?: emptyList()) + userMessage

        viewModelScope.launch(Dispatchers.Default) {
            _isLoading.postValue(true)
            val response = processUserMessage(messageText)
            val assistantMessage = ChatMessage(
                text = response,
                isUser = false
            )
            _messages.postValue((_messages.value ?: emptyList()) + assistantMessage)
            _isLoading.postValue(false)
        }
    }

    private fun processUserMessage(message: String): String {
        return try {
            // Search knowledge base for relevant context
            val context = searchKnowledgeBase(message)

            // Build prompt with context
            val prompt = buildPrompt(message, context)

            // Generate response using LLM
            llmEngine?.generateResponse(prompt) ?: "Unable to generate response"
        } catch (e: Exception) {
            "Error processing message: ${e.message}"
        }
    }

    private fun searchKnowledgeBase(query: String): String {
        return try {
            val results = knowledgeBase?.search(query, topK = 3) ?: emptyList()
            if (results.isNotEmpty()) {
                results.joinToString("\n---\n")
            } else {
                ""
            }
        } catch (e: Exception) {
            ""
        }
    }

    private fun buildPrompt(userMessage: String, context: String): String {
        return if (context.isNotEmpty()) {
            """
            Context:
            $context
            
            User: $userMessage
            Assistant:
            """.trimIndent()
        } else {
            "User: $userMessage\nAssistant:"
        }
    }

    private fun addSampleDocuments() {
        try {
            knowledgeBase?.addDocument(
                "About Fonte",
                "system",
                "Fonte is a lightweight offline LLM application designed for devices with limited resources. " +
                        "It uses TensorFlow Lite for efficient on-device inference and semantic search for knowledge retrieval."
            )
            knowledgeBase?.addDocument(
                "TensorFlow Lite",
                "system",
                "TensorFlow Lite is an open-source deep learning framework for on-device inference. " +
                        "It enables fast and private machine learning on mobile and embedded devices."
            )
            knowledgeBase?.addDocument(
                "Knowledge Base",
                "system",
                "The knowledge base stores documents and their embeddings. " +
                        "It uses cosine similarity to find semantically related documents for query context."
            )
        } catch (e: Exception) {
            // Silently fail during sample document addition
        }
    }

    override fun onCleared() {
        super.onCleared()
        llmEngine?.shutdown()
        knowledgeBase?.close()
    }
}
