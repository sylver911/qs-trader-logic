import os
import requests
from flask import Flask, jsonify
from ibind import IbkrClient, ibind_logs_initialize

ibind_logs_initialize(log_to_file=False)

app = Flask(__name__)

# Config
IBEAM_URL = os.getenv('IBEAM_URL', 'http://ibeam-deploy.railway.internal:5000')
ACCOUNT_ID = os.getenv('IB_ACCOUNT_ID', 'DU8875169')

# Fix: add http:// if missing
if not IBEAM_URL.startswith('http'):
    IBEAM_URL = f'http://{IBEAM_URL}'

print(f"🚀 Server starting...")
print(f"📡 IBeam URL: {IBEAM_URL}")
print(f"📊 Account ID: {ACCOUNT_ID}")


@app.route('/')
def index():
    return jsonify({
        "status": "running",
        "message": "Test endpoints available",
        "endpoints": {
            "health": "/health",
            "test_http": "/test-http",
            "test_ibind": "/test-ibind"
        }
    })


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/test-http')
def test_http():
    """Test with raw HTTP requests"""
    try:
        print("\n🔄 Testing with raw HTTP requests...")

        url = f"{IBEAM_URL}/v1/api/iserver/auth/status"
        print(f"📍 Calling: {url}")

        response = requests.post(url, timeout=10, verify=False)

        print(f"✅ Status Code: {response.status_code}")
        print(f"📦 Response: {response.text}")

        return jsonify({
            "success": True,
            "method": "raw_http",
            "status_code": response.status_code,
            "response": response.json() if response.status_code == 200 else response.text,
            "url": url
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({
            "success": False,
            "method": "raw_http",
            "error": str(e)
        }), 500


@app.route('/test-ibind')
def test_ibind():
    """Test with IBind client"""
    try:
        print("\n🔄 Testing with IBind...")
        print(f"📍 URL: {IBEAM_URL}")
        print(f"📊 Account: {ACCOUNT_ID}")

        client = IbkrClient(
            url=IBEAM_URL,
            account_id=ACCOUNT_ID,
            cacert=False,
            timeout=10
        )

        print("✅ IbkrClient initialized")

        # Tickle
        print("📍 Calling tickle()...")
        tickle = client.tickle()
        print(f"✅ Tickle response: {tickle.data}")

        # Accounts
        print("📍 Calling portfolio_accounts()...")
        accounts = client.portfolio_accounts()
        print(f"✅ Accounts: {accounts.data}")

        return jsonify({
            "success": True,
            "method": "ibind",
            "tickle": tickle.data,
            "accounts": accounts.data
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

        return jsonify({
            "success": False,
            "method": "ibind",
            "error": str(e)
        }), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    print(f"\n🌐 Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)

