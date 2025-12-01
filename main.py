import os
from pathlib import Path
from ibind_adapter import IBTradingClient

# IBeam címe
ibeam_url = os.getenv('IBEAM_ADDRESS', 'localhost:5000')
if not ibeam_url.startswith('http'):
    ibeam_url = f'http://{ibeam_url}'

print(f"Connecting to: {ibeam_url}")

# Account ID
account_id = os.getenv('IB_ACCOUNT_ID', 'YOUR_ACCOUNT_ID_HERE')

# Dummy cacert létrehozása ha nincs
cacert_path = '/tmp/dummy_cert.pem'
if not Path(cacert_path).exists():
    Path(cacert_path).touch()
    print(f"Created dummy cert at {cacert_path}")

try:
    client = IBTradingClient(
        account_id=account_id,
        base_url=ibeam_url,
        cacert=cacert_path,  # Dummy cert
        log_level='INFO',
        auto_confirm_orders=True
    )

    # Connection check
    print("\n=== Connection Check ===")
    if client.check_connection():
        print("✅ Gateway is healthy!")
    else:
        print("❌ Gateway health check failed")
        exit(1)

    # Tickle
    print("\n=== Tickle ===")
    tickle_response = client.tickle()
    print(f"Tickle: {tickle_response}")

    # Accounts
    print("\n=== Accounts ===")
    accounts = client.get_accounts()
    print(f"Accounts: {accounts}")

    print("\n✅ Connection successful!")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback

    traceback.print_exc()