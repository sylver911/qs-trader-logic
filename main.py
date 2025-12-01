import os
import requests
from flask import Flask, jsonify

app = Flask(__name__)

# Config
IBEAM_URL = os.getenv('IBEAM_URL', 'https://ibeam-deploy-production.up.railway.app')
ACCOUNT_ID = os.getenv('IB_ACCOUNT_ID', 'DU8875169')

print(f"🚀 Server starting...")
print(f"📡 IBeam URL: {IBEAM_URL}")
print(f"📊 Account ID: {ACCOUNT_ID}")


@app.route('/')
def index():
    return jsonify({
        "status": "running",
        "message": "Call /test to test IBeam auth status",
        "endpoints": {
            "health": "/health",
            "test": "/test"
        }
    })


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/test')
def test_auth_status():
    """Test IBeam auth status endpoint"""
    try:
        print("\n🔄 Testing IBeam auth status...")

        url = f"{IBEAM_URL}/v1/api/iserver/auth/status"
        print(f"📍 Calling: {url}")

        response = requests.post(url, timeout=10, verify=False)

        print(f"✅ Status Code: {response.status_code}")
        print(f"📦 Response: {response.text}")

        return jsonify({
            "success": True,
            "status_code": response.status_code,
            "response": response.json() if response.status_code == 200 else response.text,
            "url": url
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "url": f"{IBEAM_URL}/v1/api/iserver/auth/status"
        }), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    print(f"\n🌐 Starting server on port {port}")
    print(f"📍 Test endpoint: http://localhost:{port}/test")
    app.run(host='0.0.0.0', port=port, debug=False)