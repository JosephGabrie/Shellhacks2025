"""
Flask server to receive Discord messages and optionally process them.
Run this alongside your Discord bot.

Install: pip install flask
Usage: python ingest_server.py
"""

from flask import Flask, request, jsonify
import json
from datetime import datetime

app = Flask(__name__)

# This should match your INGEST_SECRET
EXPECTED_SECRET = "dev-secret"

@app.route('/ingest', methods=['POST'])
def ingest_message():
    # Verify the secret
    secret = request.headers.get('X-Ingest-Secret')
    if secret != EXPECTED_SECRET:
        return jsonify({"error": "Invalid secret"}), 401
    
    try:
        # Get the JSON data from Discord bot
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Print the received message (you can process this however you want)
        print(f"\n--- Received Discord Message ---")
        print(f"Time: {datetime.now().isoformat()}")
        print(f"Author: {data.get('author', {}).get('name', 'Unknown')}")
        print(f"Content: {data.get('content', '')}")
        print(f"Channel: {data.get('channel', {}).get('name', 'Unknown')}")
        if data.get('guild'):
            print(f"Server: {data.get('guild', {}).get('name', 'Unknown')}")
        print(f"Full JSON: {json.dumps(data, indent=2)}")
        print("--------------------------------\n")
        
        # You can add your processing logic here
        # For example, save to file, send to another service, etc.
        
        # Return success response
        return jsonify({
            "status": "success", 
            "message": "Message received and processed",
            "processed_at": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        print(f"Error processing message: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

if __name__ == '__main__':
    print("Starting ingest server on http://127.0.0.1:3000")
    print("Endpoint: http://127.0.0.1:3000/ingest")
    print("Health check: http://127.0.0.1:3000/health")
    app.run(host='127.0.0.1', port=3000, debug=True)