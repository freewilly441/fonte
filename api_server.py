"""
Fonte REST API Server for Mobile (Capacitor)
Lightweight Flask API exposing LLM chat functionality for mobile clients
Designed to run locally on Android device via Chaquopy
"""

import json
import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

try:
    from flask import Flask, request, jsonify, send_from_directory
    from flask_cors import CORS
except ImportError:
    print("Error: Flask not installed. Run: pip install flask flask-cors")
    sys.exit(1)

# Import Fonte backend modules
try:
    import llm as llm_api
    import kb
    import config
    import utils
    from app_state import AppState, load_state, save_state
    from error_mapper import map_exception, to_ui_error
except ImportError as e:
    print(f"Error importing Fonte modules: {e}")
    sys.exit(1)

# Configuration
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
API_PORT = int(os.getenv("FONTE_API_PORT", 9000))  # Using port 9000
API_HOST = os.getenv("FONTE_API_HOST", "127.0.0.1")
DEBUG = os.getenv("FONTE_DEBUG", "0") == "1"

# Initialize Flask app
app = Flask(__name__, static_folder=None)
CORS(app)

# Global state
app_state: Optional[AppState] = None
kb_db_path: Optional[Path] = None
llm_model = None


def init_app_state():
    """Initialize app state and knowledge base on startup"""
    global app_state, kb_db_path

    try:
        app_state = load_state(Path(DATA_DIR / "app_state.json"))
        print("[API] App state loaded")

        # Initialize knowledge base path
        kb_db_path = DATA_DIR / "kb.sqlite"
        if kb_db_path.exists():
            print("[API] Knowledge base found")
        else:
            print("[API] Initializing knowledge base...")
            kb.init_db(kb_db_path)
            print("[API] Knowledge base initialized")

        # LLM will be loaded on-demand (it's slow to initialize)
        print("[API] LLM will load on first chat request")

        return True
    except Exception as e:
        print(f"[API] Error initializing app state: {e}")
        traceback.print_exc()
        return False


# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "version": "1.0.0",
        "service": "fonte-api"
    }), 200


@app.route("/api/status", methods=["GET"])
def status():
    """Get API and LLM status"""
    try:
        kb_ready = kb_db_path is not None and kb_db_path.exists()

        return jsonify({
            "api_ready": True,
            "llm_ready": llm_model is not None,
            "kb_ready": kb_ready,
            "app_state_loaded": app_state is not None,
            "message": "API is healthy and ready for chat"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================================
# LLM Chat Endpoints
# ============================================================================

@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Chat endpoint - send message to LLM, get response

    Request body:
    {
        "message": "What is...",
        "conversation_id": "optional-id",
        "search_docs": true,
        "language": "en"
    }

    Response:
    {
        "response": "Answer...",
        "conversation_id": "id",
        "sources": [],
        "success": true
    }
    """
    try:
        data = request.get_json() or {}
        message = data.get("message", "").strip()

        if not message:
            return jsonify({"error": "Message required"}), 400

        # Optional parameters
        conversation_id = data.get("conversation_id", "")
        search_docs = data.get("search_docs", True)

        # Echo response for testing (LLM will be integrated later)
        response = f"Echo: {message}"

        # If search_docs enabled, try to search KB
        sources = []
        if search_docs and kb_db_path:
            try:
                search_results = kb.search(kb_db_path, message, limit=3)
                sources = [
                    {
                        "rowid": r.rowid,
                        "title": r.title,
                        "text": r.chunk_text[:100],  # First 100 chars
                        "source": r.source
                    }
                    for r in search_results
                ]
            except Exception as e:
                print(f"[API] Search error: {e}")

        return jsonify({
            "response": response,
            "conversation_id": conversation_id,
            "sources": sources,
            "timestamp": datetime.now().isoformat(),
            "success": True
        }), 200

    except Exception as e:
        error_msg = str(e)
        print(f"[API] Chat error: {error_msg}")
        print(f"[API] Error type: {type(e).__name__}")
        traceback.print_exc()
        return jsonify({
            "error": error_msg if error_msg else "Unknown error in chat",
            "error_type": type(e).__name__,
            "success": False
        }), 500


@app.route("/api/search", methods=["POST"])
def search_documents():
    """
    Search knowledge base

    Request: {"query": "search term", "limit": 10}
    Response: {"results": [...]}
    """
    try:
        if not kb_db_path or not kb_db_path.exists():
            return jsonify({"error": "Knowledge base not initialized"}), 503

        data = request.get_json() or {}
        query = data.get("query", "").strip()
        limit = data.get("limit", 10)

        if not query:
            return jsonify({"error": "Query required"}), 400

        results = kb.search(kb_db_path, query, limit=limit)

        # Convert results to JSON-serializable format
        results_data = [
            {
                "rowid": r.rowid,
                "title": r.title,
                "text": r.chunk_text,
                "source": r.source,
                "score": r.score
            }
            for r in results
        ]

        return jsonify({
            "results": results_data,
            "count": len(results),
            "success": True
        }), 200

    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500


# ============================================================================
# Configuration Endpoints
# ============================================================================

@app.route("/api/config", methods=["GET"])
def get_app_config():
    """Get mobile-safe configuration"""
    try:
        cfg = config.load_config(DATA_DIR / "config.json") or {}

        # Return only mobile-safe config (exclude paths, secrets, etc.)
        return jsonify({
            "language": cfg.get("language", "en"),
            "theme": cfg.get("theme", "dark"),
            "llm_model": cfg.get("llm_model", ""),
            "search_enabled": cfg.get("search_enabled", True),
            "api_port": API_PORT,
            "api_host": API_HOST
        }), 200
    except Exception as e:
        return jsonify({"error": str(e), "config": {}}), 200  # Return empty config on error


@app.route("/api/config", methods=["POST"])
def update_config():
    """Update mobile configuration"""
    try:
        data = request.get_json() or {}

        # Only allow safe config updates from mobile
        allowed_keys = {"language", "theme"}
        safe_updates = {k: v for k, v in data.items() if k in allowed_keys}

        if safe_updates:
            cfg = config.get_config()
            cfg.update(safe_updates)
            config.save_config(cfg)

        return jsonify({"success": True, "updated": safe_updates}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Static Files (Web UI)
# ============================================================================

@app.route("/", methods=["GET"])
def serve_index():
    """Serve index.html"""
    www_dir = APP_DIR / "capacitor-mobile" / "www"
    if www_dir.exists():
        return send_from_directory(str(www_dir), "index.html")
    return jsonify({"error": "Web UI not found"}), 404


@app.route("/<path:path>", methods=["GET"])
def serve_static(path):
    """Serve static files (CSS, JS)"""
    www_dir = APP_DIR / "capacitor-mobile" / "www"
    if www_dir.exists():
        file_path = www_dir / path
        if file_path.exists() and file_path.is_file():
            parent = str(www_dir)
            return send_from_directory(parent, path)
    return jsonify({"error": "File not found"}), 404


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error"}), 500


# ============================================================================
# Startup & Shutdown
# ============================================================================

def run_server():
    """Run Flask development server"""
    print(f"[API] Starting Fonte REST API on {API_HOST}:{API_PORT}")
    print(f"[API] Debug mode: {DEBUG}")

    if not init_app_state():
        print("[API] Warning: Could not initialize app state")

    app.run(
        host=API_HOST,
        port=API_PORT,
        debug=DEBUG,
        use_reloader=False,
        threaded=True
    )


if __name__ == "__main__":
    run_server()
