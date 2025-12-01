import os
from ibind import IbkrClient, ibind_logs_initialize

# Initialize IBind logging
ibind_logs_initialize(log_to_file=False)

# IBeam URL - Railway internal vagy public
ibeam_url = os.getenv('IBEAM_URL', 'http://ibeam-deploy.railway.internal:5000')

print(f"🔗 Connecting to IBeam at: {ibeam_url}")

# Account ID
account_id = os.getenv('IB_ACCOUNT_ID', 'DU8875169')
print(f"📊 Account ID: {account_id}")

try:
    print("\n⏳ Initializing IbkrClient...")

    # Egyszerű inicializálás - cacert=False teljesen valid!
    client = IbkrClient(
        url=ibeam_url,
        account_id=account_id,
        cacert=False,  # Nincs szükség cacert-re!
        timeout=10
    )

    print("✅ Client initialized")

    # 1. Health check
    print("\n=== 🏥 Health Check ===")
    health = client.check_health()
    print(f"Health: {health}")

    # 2. Tickle
    print("\n=== 🔄 Tickle ===")
    tickle = client.tickle()
    print(f"Response: {tickle.data}")

    # 3. Accounts
    print("\n=== 👤 Accounts ===")
    accounts = client.portfolio_accounts()
    print(f"Accounts: {accounts.data}")

    # 4. Ledger (Balance)
    print("\n=== 💰 Balance ===")
    ledger = client.get_ledger()
    for currency, subledger in ledger.data.items():
        print(f"  {currency}:")
        print(f"    Cash balance: ${subledger.get('cashbalance', 0)}")
        print(f"    Net liquidation: ${subledger.get('netliquidationvalue', 0)}")
        print(f"    Stock market value: ${subledger.get('stockmarketvalue', 0)}")

    # 5. Positions
    print("\n=== 📈 Positions ===")
    positions = client.positions()
    if positions.data:
        for pos in positions.data:
            ticker = pos.get('ticker', 'N/A')
            quantity = pos.get('position', 0)
            value = pos.get('mktValue', 0)
            print(f"  {ticker}: {quantity} shares (${value})")
    else:
        print("  No positions")

    print("\n✅✅✅ ALL CHECKS PASSED! ✅✅✅")

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback

    traceback.print_exc()