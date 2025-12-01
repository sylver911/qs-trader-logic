import os
from flask import Flask, jsonify
from ibind import IbkrClient, ibind_logs_initialize

ibind_logs_initialize(log_to_file=False)

app = Flask(__name__)

# Config
IBEAM_URL = os.getenv('IBEAM_URL', 'http://ibeam-deploy.railway.internal:5000')
ACCOUNT_ID = os.getenv('IB_ACCOUNT_ID', 'DU8875169')

print(f"🚀 Server starting...")
print(f"📡 IBeam URL: {IBEAM_URL}")
print(f"📊 Account ID: {ACCOUNT_ID}")


@app.route('/')
def index():
    return jsonify({
        "status": "running",
        "message": "Call /test to test IBeam connection",
        "endpoints": {
            "health": "/health",
            "test": "/test",
            "accounts": "/accounts",
            "balance": "/balance",
            "positions": "/positions"
        }
    })


@app.route('/health')
def health():
    return jsonify({"status": "ok"})


@app.route('/test')
def test_connection():
    """On-demand IBeam connection test"""
    try:
        print("\n🔄 Testing IBeam connection...")

        client = IbkrClient(
            url=IBEAM_URL,
            account_id=ACCOUNT_ID,
            cacert=False,
            timeout=10
        )

        # Tickle
        tickle = client.tickle()

        return jsonify({
            "success": True,
            "tickle": tickle.data,
            "message": "IBeam connection successful!"
        })

    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "message": "IBeam connection failed"
        }), 500


@app.route('/accounts')
def get_accounts():
    """Get accounts"""
    try:
        client = IbkrClient(
            url=IBEAM_URL,
            account_id=ACCOUNT_ID,
            cacert=False,
            timeout=10
        )

        accounts = client.portfolio_accounts()

        return jsonify({
            "success": True,
            "accounts": accounts.data
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/balance')
def get_balance():
    """Get balance"""
    try:
        client = IbkrClient(
            url=IBEAM_URL,
            account_id=ACCOUNT_ID,
            cacert=False,
            timeout=10
        )

        ledger = client.get_ledger()

        balance_data = {}
        for currency, subledger in ledger.data.items():
            balance_data[currency] = {
                "cash": subledger.get('cashbalance', 0),
                "net_liquidation": subledger.get('netliquidationvalue', 0),
                "stock_market_value": subledger.get('stockmarketvalue', 0)
            }

        return jsonify({
            "success": True,
            "balance": balance_data
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/positions')
def get_positions():
    """Get positions"""
    try:
        client = IbkrClient(
            url=IBEAM_URL,
            account_id=ACCOUNT_ID,
            cacert=False,
            timeout=10
        )

        positions = client.positions()

        positions_data = []
        if positions.data:
            for pos in positions.data:
                positions_data.append({
                    "ticker": pos.get('ticker'),
                    "quantity": pos.get('position'),
                    "market_value": pos.get('mktValue'),
                    "avg_price": pos.get('avgPrice')
                })

        return jsonify({
            "success": True,
            "positions": positions_data,
            "count": len(positions_data)
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8000))
    print(f"\n🌐 Starting server on port {port}")
    print(f"📍 Test endpoint: http://localhost:{port}/test")
    app.run(host='0.0.0.0', port=port, debug=False)