/**
 * Fonte Mobile App - Main UI Logic
 * Lightweight chat interface for Fonte LLM
 */

class FonteMobileApp {
    constructor() {
        // DOM Elements
        this.app = document.getElementById('app');
        this.messagesContainer = document.getElementById('messages');
        this.chatForm = document.getElementById('chat-form');
        this.messageInput = document.getElementById('message-input');
        this.sendBtn = document.getElementById('send-btn');
        this.loadingOverlay = document.getElementById('loading');
        this.statusBar = document.getElementById('status-bar');
        this.statusText = document.getElementById('status-text');
        this.errorDialog = document.getElementById('error-dialog');
        this.errorText = document.getElementById('error-text');
        this.errorCloseBtn = document.getElementById('error-close-btn');
        this.menuBtn = document.getElementById('menu-btn');
        this.menu = document.getElementById('menu');
        this.menuOverlay = document.getElementById('menu-overlay');
        this.clearBtn = document.getElementById('clear-btn');
        this.settingsBtn = document.getElementById('settings-btn');
        this.aboutBtn = document.getElementById('about-btn');

        // State
        this.messages = [];
        this.isLoading = false;
        this.conversationId = this._generateId();
        this.isApiReady = false;

        // Initialize
        this._init();
    }

    /**
     * Initialize app
     */
    async _init() {
        this._attachEventListeners();
        await this._checkAPIHealth();
        this._restoreMessages();
        this._focusInput();
        this._showEmptyState();
    }

    /**
     * Attach event listeners
     */
    _attachEventListeners() {
        this.chatForm.addEventListener('submit', e => this._handleSubmit(e));
        this.sendBtn.addEventListener('click', e => this._handleSubmit(e));
        this.messageInput.addEventListener('keydown', e => this._handleKeyDown(e));
        this.menuBtn.addEventListener('click', () => this._toggleMenu());
        this.menuOverlay.addEventListener('click', () => this._closeMenu());
        this.clearBtn.addEventListener('click', () => this._clearChat());
        this.settingsBtn.addEventListener('click', () => this._showSettings());
        this.aboutBtn.addEventListener('click', () => this._showAbout());
        this.errorCloseBtn.addEventListener('click', () => this._closeError());

        // Close menu when item clicked
        [this.clearBtn, this.settingsBtn, this.aboutBtn].forEach(btn => {
            btn.addEventListener('click', () => this._closeMenu());
        });
    }

    /**
     * Check API health on startup
     */
    async _checkAPIHealth() {
        try {
            this._showStatus('Checking connection...');
            const healthy = await window.api.checkHealth();

            if (healthy) {
                const status = await window.api.getStatus();
                if (status.llm_ready) {
                    this._showStatus('Ready');
                    this.isApiReady = true;
                    setTimeout(() => this._hideStatus(), 2000);
                } else {
                    this._showStatus('Loading models...');
                }
            }
        } catch (error) {
            console.error('Health check failed:', error);
            this._showError('Connection failed', 'Cannot connect to Fonte API. Ensure the app is running.');
            this.isApiReady = false;
        }
    }

    /**
     * Handle form submission
     */
    async _handleSubmit(e) {
        e.preventDefault();

        const message = this.messageInput.value.trim();
        if (!message) return;

        if (this.isLoading) return;

        // Disable input
        this.messageInput.value = '';
        this.messageInput.disabled = true;
        this.sendBtn.disabled = true;
        this.isLoading = true;

        // Add user message to UI
        this._addMessage('user', message);

        // Show loading
        this._showLoading(true);

        try {
            // Call API
            const result = await window.api.chat(message, {
                conversationId: this.conversationId,
                searchDocs: true
            });

            if (result.success) {
                // Add assistant response
                this._addMessage('assistant', result.response);
                this._saveMessages();
            } else {
                throw new Error(result.error || 'Unknown error');
            }
        } catch (error) {
            console.error('Chat error:', error);
            this._showError('Error', error.message || 'Failed to get response from Fonte');

            // Remove the last user message if there's an error
            this._removeLastMessage();
        } finally {
            // Re-enable input
            this._showLoading(false);
            this.messageInput.disabled = false;
            this.sendBtn.disabled = false;
            this.isLoading = false;
            this._focusInput();
        }
    }

    /**
     * Handle message input keydown
     */
    _handleKeyDown(e) {
        // Send on Enter (but not Shift+Enter)
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            this._handleSubmit(e);
        }
    }

    /**
     * Add message to chat
     */
    _addMessage(role, content) {
        const now = new Date();
        const timeStr = now.toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
        });

        const message = {
            id: this._generateId(),
            role,
            content,
            timestamp: now.toISOString(),
            timeStr
        };

        this.messages.push(message);
        this._renderMessage(message);
        this._scrollToBottom();
    }

    /**
     * Render single message in DOM
     */
    _renderMessage(message) {
        const div = document.createElement('div');
        div.className = `message ${message.role}`;
        div.id = `msg-${message.id}`;

        const bubble = document.createElement('div');
        bubble.className = 'message-bubble';
        bubble.textContent = message.content;

        const time = document.createElement('div');
        time.className = 'message-time';
        time.textContent = message.timeStr;

        div.appendChild(bubble);
        div.appendChild(time);

        this.messagesContainer.appendChild(div);
    }

    /**
     * Remove last message (for error cases)
     */
    _removeLastMessage() {
        if (this.messages.length > 0) {
            const lastMsg = this.messages.pop();
            const el = document.getElementById(`msg-${lastMsg.id}`);
            if (el) el.remove();
        }
    }

    /**
     * Clear chat history
     */
    _clearChat() {
        if (!confirm('Clear all messages?')) return;

        this.messages = [];
        this.conversationId = this._generateId();
        this.messagesContainer.innerHTML = '';
        this._saveMessages();
        this._showEmptyState();
        this._focusInput();
    }

    /**
     * Show empty state
     */
    _showEmptyState() {
        if (this.messages.length === 0 && !this.messagesContainer.querySelector('.empty-state')) {
            const div = document.createElement('div');
            div.className = 'empty-state';
            div.innerHTML = `
                <div class="empty-state-icon">💬</div>
                <p class="empty-state-text">Start by asking Fonte a question</p>
            `;
            this.messagesContainer.appendChild(div);
        }
    }

    /**
     * Remove empty state
     */
    _removeEmptyState() {
        const el = this.messagesContainer.querySelector('.empty-state');
        if (el) el.remove();
    }

    /**
     * Toggle menu
     */
    _toggleMenu() {
        const isOpen = this.menu.style.display !== 'none';
        if (isOpen) {
            this._closeMenu();
        } else {
            this.menu.style.display = 'flex';
            this.menuOverlay.style.display = 'block';
        }
    }

    /**
     * Close menu
     */
    _closeMenu() {
        this.menu.style.display = 'none';
        this.menuOverlay.style.display = 'none';
    }

    /**
     * Show settings (placeholder)
     */
    _showSettings() {
        this._showError('Settings', 'Settings coming soon');
    }

    /**
     * Show about (placeholder)
     */
    _showAbout() {
        const about = `Fonte Mobile
Version 1.0.0

Lightweight local LLM chat powered by Capacitor and Flask

© 2026 Aethermark Systems LLC`;
        this._showError('About', about);
    }

    /**
     * Show error dialog
     */
    _showError(title, message) {
        const header = this.errorDialog.querySelector('h2');
        if (header) header.textContent = title;
        this.errorText.textContent = message;
        this.errorDialog.style.display = 'flex';
    }

    /**
     * Close error dialog
     */
    _closeError() {
        this.errorDialog.style.display = 'none';
    }

    /**
     * Show loading overlay
     */
    _showLoading(show) {
        this.loadingOverlay.style.display = show ? 'flex' : 'none';
    }

    /**
     * Show status message
     */
    _showStatus(text) {
        this.statusText.textContent = text;
        this.statusBar.style.display = 'block';
    }

    /**
     * Hide status message
     */
    _hideStatus() {
        this.statusBar.style.display = 'none';
    }

    /**
     * Scroll to bottom of messages
     */
    _scrollToBottom() {
        setTimeout(() => {
            this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
        }, 0);
    }

    /**
     * Focus input
     */
    _focusInput() {
        this.messageInput.focus();
    }

    /**
     * Save messages to local storage
     */
    _saveMessages() {
        try {
            const data = {
                messages: this.messages,
                conversationId: this.conversationId,
                timestamp: new Date().toISOString()
            };
            localStorage.setItem('fonte_chat_history', JSON.stringify(data));
        } catch (error) {
            console.warn('Failed to save chat history:', error);
        }
    }

    /**
     * Restore messages from local storage
     */
    _restoreMessages() {
        try {
            const data = localStorage.getItem('fonte_chat_history');
            if (data) {
                const parsed = JSON.parse(data);
                this.messages = parsed.messages || [];
                this.conversationId = parsed.conversationId || this._generateId();

                // Re-render messages
                this.messagesContainer.innerHTML = '';
                this.messages.forEach(msg => this._renderMessage(msg));

                if (this.messages.length > 0) {
                    this._scrollToBottom();
                }
            }
        } catch (error) {
            console.warn('Failed to restore chat history:', error);
        }
    }

    /**
     * Generate unique ID
     */
    _generateId() {
        return `${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }
}

/**
 * Initialize app when DOM is ready
 */
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.app = new FonteMobileApp();
    });
} else {
    window.app = new FonteMobileApp();
}
