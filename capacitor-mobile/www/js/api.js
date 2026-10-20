/**
 * Fonte Mobile API Client
 * Lightweight HTTP client for Fonte REST API
 */

class FonteAPI {
    constructor(baseURL = 'http://10.0.2.2:9000') {  // 10.0.2.2 is how Android emulator refers to host
        this.baseURL = baseURL;
        this.timeout = 30000; // 30 seconds
        this.retryCount = 3;
        this.retryDelay = 1000; // 1 second
    }

    /**
     * Make HTTP request with retry logic
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const defaults = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            timeout: this.timeout
        };

        const config = { ...defaults, ...options };
        let lastError = null;

        for (let attempt = 0; attempt < this.retryCount; attempt++) {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), config.timeout);

                const response = await fetch(url, {
                    ...config,
                    signal: controller.signal
                });

                clearTimeout(timeoutId);

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                return await response.json();
            } catch (error) {
                lastError = error;

                // Don't retry on client errors (4xx)
                if (error.message && error.message.includes('HTTP 4')) {
                    throw error;
                }

                // Wait before retry
                if (attempt < this.retryCount - 1) {
                    await this._sleep(this.retryDelay * (attempt + 1));
                }
            }
        }

        throw new Error(
            `API request failed after ${this.retryCount} attempts: ${lastError.message}`
        );
    }

    /**
     * Check if API is healthy
     */
    async checkHealth() {
        try {
            const result = await this.request('/api/health');
            return result.status === 'healthy';
        } catch (error) {
            console.error('Health check failed:', error);
            return false;
        }
    }

    /**
     * Get API status
     */
    async getStatus() {
        return this.request('/api/status');
    }

    /**
     * Send message to LLM
     */
    async chat(message, options = {}) {
        const body = {
            message,
            conversation_id: options.conversationId || '',
            search_docs: options.searchDocs !== false,
            language: options.language || 'en'
        };

        return this.request('/api/chat', {
            method: 'POST',
            body: JSON.stringify(body)
        });
    }

    /**
     * Search knowledge base
     */
    async search(query, limit = 10) {
        const body = { query, limit };

        return this.request('/api/search', {
            method: 'POST',
            body: JSON.stringify(body)
        });
    }

    /**
     * Get configuration
     */
    async getConfig() {
        return this.request('/api/config');
    }

    /**
     * Update configuration
     */
    async updateConfig(updates) {
        return this.request('/api/config', {
            method: 'POST',
            body: JSON.stringify(updates)
        });
    }

    /**
     * Utility: sleep for milliseconds
     */
    _sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// Create global API instance
window.api = new FonteAPI();
