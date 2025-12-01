import os
from ibind import IbkrClient, ibind_logs_initialize

ibind_logs_initialize(log_to_file=False)

ibeam_url = os.getenv('IBEAM_URL', 'http://ibeam-deploy.railway.internal:5000')
print(f"🔗 Connecting to IBeam at: {ibeam_url}")

account_id = os.getenv('IB_ACCOUNT_ID', 'DU8875169')
print(f"📊 Account ID: {account_id}")

try:
    print("\n⏳ Initializing IbkrClient...")

    client = IbkrClient(
        url=ibeam_url,
        account_id=account_id,
        cacert=False,
        timeout=10,
        base_route='/v1/api/'  # <--- Ez az API prefix!
    )

    print("✅ Client initialized")

    # Health check
    print("\n=== 🏥 Health Check ===")
    health = client.check_health()
    print(f"Health: {health}")

    # Tickle
    print("\n=== 🔄 Tickle ===")
    tickle = client.tickle()
    print(f"Response: {tickle.data}")

    # Accounts
    print("\n=== 👤 Accounts ===")
    accounts = client.portfolio_accounts()
    print(f"Accounts: {accounts.data}")

    # Ledger
    print("\n=== 💰 Balance ===")
    ledger = client.get_ledger()
    for currency, subledger in ledger.data.items():
        print(f"  {currency}:")
        print(f"    Cash: ${subledger.get('cashbalance', 0)}")
        print(f"    Net Liq: ${subledger.get('netliquidationvalue', 0)}")

    # Positions
    print("\n=== 📈 Positions ===")
    positions = client.positions()
    if positions.data:
        for pos in positions.data:
            print(f"  {pos.get('ticker')}: {pos.get('position')} @ ${pos.get('mktValue')}")
    else:
        print("  No positions")

    print("\n✅✅✅ ALL CHECKS PASSED! ✅✅✅")

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback

    traceback.print_exc()