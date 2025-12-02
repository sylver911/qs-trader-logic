import os
from ibind import IbkrClient

# Railway-n a belső cím általában így néz ki: servicename.railway.internal:5000
# De ha IBEAM_ADDRESS-ben domain van (pl. ibeam-production.up.railway.app),
# akkor HTTPS-t kell használni

ibeam_address = os.getenv('IBEAM_ADDRESS', 'localhost:5000')

# Ha nem tartalmaz http-t, adjuk hozzá
if not ibeam_address.startswith('http'):
    # Railway domain esetén HTTPS, különben HTTP
    if 'railway.app' in ibeam_address:
        base_url = f'https://{ibeam_address}'
    else:
        base_url = f'http://{ibeam_address}'
else:
    base_url = ibeam_address

print(f"Connecting to IBeam at: {base_url}")

# IbkrClient létrehozása
client = IbkrClient(base_url=base_url)

try:
    # 1. Authentikációs státusz ellenőrzése
    print("\n=== Authentication Status ===")
    auth_status = client.tickle()
    print(f"Auth status: {auth_status}")

    # 2. Portfolio accounts lekérdezése
    print("\n=== Portfolio Accounts ===")
    accounts = client.portfolio_accounts()
    print(f"Accounts: {accounts}")

    # 3. Account summary (ha van account)
    if accounts:
        account_id = accounts[0].get('accountId')
        print(f"\n=== Account Summary for {account_id} ===")
        summary = client.portfolio_account_summary(account_id=account_id)
        print(f"Summary: {summary}")

    print("\n✅ Connection successful!")

except Exception as e:
    print(f"\n❌ Error: {e}")
    print(f"Make sure IBeam is running and accessible at {base_url}")