#!/usr/bin/env python3
"""
Simple test API for Fonte Mobile
"""
from flask import Flask, jsonify, request
from flask_cors import CORS
import json

app = Flask(__name__)
CORS(app)

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "version": "test"})

@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json() or {}
        message = data.get("message", "").strip()

        if not message:
            return jsonify({"error": "Message required"}), 400

        return jsonify({
            "response": f"You said: {message}",
            "success": True
        }), 200
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

if __name__ == "__main__":
    port = 5555  # Use different port to avoid conflicts
    print(f"[TEST] Starting test API on 127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
