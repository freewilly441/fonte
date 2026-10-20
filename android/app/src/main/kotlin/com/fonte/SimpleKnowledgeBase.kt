package com.fonte

import android.content.ContentValues
import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper
import android.util.Log
import java.nio.ByteBuffer
import kotlin.math.sqrt

class SimpleKnowledgeBase(context: Context) : SQLiteOpenHelper(context, DATABASE_NAME, null, DATABASE_VERSION) {
    companion object {
        private const val TAG = "SimpleKnowledgeBase"
        private const val DATABASE_NAME = "fonte_kb.db"
        private const val DATABASE_VERSION = 1
        private const val TABLE_DOCUMENTS = "documents"
        private const val COL_ID = "id"
        private const val COL_TITLE = "title"
        private const val COL_SOURCE = "source"
        private const val COL_TEXT = "text"
        private const val COL_EMBEDDING = "embedding"
        private const val COL_CREATED_AT = "created_at"
        private const val EMBEDDING_DIM = 384
        private const val SEARCH_TOP_K = 3
    }

    private var db: SQLiteDatabase? = null
    private val embeddingModel = SimpleEmbeddingModel()

    override fun onCreate(database: SQLiteDatabase) {
        val createTableSQL = """
            CREATE TABLE $TABLE_DOCUMENTS (
                $COL_ID INTEGER PRIMARY KEY AUTOINCREMENT,
                $COL_TITLE TEXT NOT NULL,
                $COL_SOURCE TEXT,
                $COL_TEXT TEXT NOT NULL,
                $COL_EMBEDDING BLOB,
                $COL_CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """.trimIndent()
        database.execSQL(createTableSQL)

        val createIndexSQL = "CREATE INDEX idx_${TABLE_DOCUMENTS}_text ON $TABLE_DOCUMENTS($COL_TEXT)"
        database.execSQL(createIndexSQL)
        
        Log.d(TAG, "Knowledge Base database created")
    }

    override fun onUpgrade(database: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        database.execSQL("DROP TABLE IF EXISTS $TABLE_DOCUMENTS")
        onCreate(database)
    }

    fun initialize(): Boolean {
        return try {
            db = writableDatabase
            Log.d(TAG, "Knowledge Base initialized")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize Knowledge Base", e)
            false
        }
    }

    fun addDocument(title: String, source: String = "", text: String): Boolean {
        return try {
            val embedding = embeddingModel.encode(text)
            val values = ContentValues().apply {
                put(COL_TITLE, title)
                put(COL_SOURCE, source)
                put(COL_TEXT, text)
                put(COL_EMBEDDING, floatArrayToBytes(embedding))
            }
            db?.insert(TABLE_DOCUMENTS, null, values)
            Log.d(TAG, "Document added: $title")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to add document", e)
            false
        }
    }

    fun search(query: String, topK: Int = SEARCH_TOP_K): List<String> {
        return try {
            val queryEmbedding = embeddingModel.encode(query)
            val cursor = db?.query(
                TABLE_DOCUMENTS,
                arrayOf(COL_TEXT, COL_EMBEDDING),
                null,
                null,
                null,
                null,
                null
            ) ?: return emptyList()

            val results = mutableListOf<Pair<String, Float>>()

            cursor.use {
                while (it.moveToNext()) {
                    val text = it.getString(0)
                    val embeddingBytes = it.getBlob(1)
                    val docEmbedding = bytesToFloatArray(embeddingBytes)

                    val similarity = cosineSimilarity(queryEmbedding, docEmbedding)
                    results.add(text to similarity)
                }
            }

            return results
                .sortedByDescending { it.second }
                .take(topK)
                .map { it.first }
        } catch (e: Exception) {
            Log.e(TAG, "Search failed", e)
            emptyList()
        }
    }

    fun getAllDocuments(): List<String> {
        return try {
            val cursor = db?.query(
                TABLE_DOCUMENTS,
                arrayOf(COL_TEXT),
                null,
                null,
                null,
                null,
                "$COL_CREATED_AT DESC"
            ) ?: return emptyList()

            val documents = mutableListOf<String>()
            cursor.use {
                while (it.moveToNext()) {
                    documents.add(it.getString(0))
                }
            }
            documents
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get documents", e)
            emptyList()
        }
    }

    fun clearDatabase(): Boolean {
        return try {
            db?.delete(TABLE_DOCUMENTS, null, null)
            Log.d(TAG, "Knowledge Base cleared")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to clear database", e)
            false
        }
    }

    private fun cosineSimilarity(a: FloatArray, b: FloatArray): Float {
        if (a.size != b.size) return 0f

        var dotProduct = 0f
        var normA = 0f
        var normB = 0f

        for (i in a.indices) {
            dotProduct += a[i] * b[i]
            normA += a[i] * a[i]
            normB += b[i] * b[i]
        }

        normA = sqrt(normA)
        normB = sqrt(normB)

        return if (normA > 0 && normB > 0) dotProduct / (normA * normB) else 0f
    }

    private fun floatArrayToBytes(array: FloatArray): ByteArray {
        val buffer = ByteBuffer.allocate(array.size * 4)
        for (value in array) {
            buffer.putFloat(value)
        }
        return buffer.array()
    }

    private fun bytesToFloatArray(bytes: ByteArray): FloatArray {
        val buffer = ByteBuffer.wrap(bytes)
        val array = FloatArray(bytes.size / 4)
        for (i in array.indices) {
            array[i] = buffer.float
        }
        return array
    }

    override fun close() {
        db?.close()
        super.close()
    }
}

class SimpleEmbeddingModel {
    fun encode(text: String): FloatArray {
        // Placeholder embedding using hash-based normalization
        val normalized = text.lowercase()
        val embedding = FloatArray(384)

        for (i in embedding.indices) {
            val charIndex = (normalized.hashCode() + i) % normalized.length
            embedding[i] = (normalized[charIndex.coerceIn(0, normalized.length - 1)].code % 100) / 100f
        }

        // Normalize to unit vector
        var norm = 0f
        for (value in embedding) {
            norm += value * value
        }
        norm = sqrt(norm)
        if (norm > 0) {
            for (i in embedding.indices) {
                embedding[i] /= norm
            }
        }

        return embedding
    }
}
