import os
from ibind_adapter import IBTradingClient

# IBeam címe Railway-ről
ibeam_url = os.getenv('IBEAM_ADDRESS', 'localhost:5000')

# Tisztítsd meg a címet
ibeam_url = ibeam_url.strip().replace('{{', '').replace('}}', '')

# Protokoll hozzáadása
if not ibeam_url.startswith('http'):
    ibeam_url = f'http://{ibeam_url}'

print(f"Connecting to IBeam at: {ibeam_url}")

try:
    # Client létrehozása
    # FIGYELEM: account_id-t add meg env variable-ből vagy itt hardcode-olva
    client = IBTradingClient(
        account_id=os.getenv('IB_ACCOUNT_ID', 'YOUR_ACCOUNT_ID_HERE'),
        base_url=ibeam_url,
        cacert=None,  # Railway-n nincs cacert
        log_level='INFO',
        auto_confirm_orders=True
    )

    # 1. Connection check
    print("\n=== Connection Check ===")
    if client.check_connection():
        print("✅ Gateway is healthy!")
    else:
        print("❌ Gateway health check failed")
        exit(1)

    # 2. Tickle (session keep-alive)
    print("\n=== Tickle ===")
    tickle_response = client.tickle()
    print(f"Tickle response: {tickle_response}")

    # 3. Account info
    print("\n=== Accounts ===")
    accounts = client.get_accounts()
    print(f"Accounts: {accounts}")

    # 4. Balance
    print("\n=== Balance ===")
    balance = client.get_account_balance()
    for currency, data in balance.items():
        print(f"{currency}: Net Liquidation = ${data['net_liquidation']:.2f}")

    # 5. Positions
    print("\n=== Positions ===")
    positions = client.get_positions()
    if positions:
        for pos in positions:
            print(f"{pos.ticker}: {pos.quantity} shares @ ${pos.avg_price:.2f} | P/L: ${pos.unrealized_pnl:.2f}")
    else:
        print("No positions")

    # 6. Live orders
    print("\n=== Live Orders ===")
    live_orders = client.get_live_orders()
    print(f"Live orders: {len(live_orders)}")
    for order in live_orders[:3]:  # Show first 3
        print(f"  {order.symbol} {order.side} {order.quantity} @ {order.order_type} - Status: {order.status}")

    print("\n✅ All checks passed!")

except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback

    traceback.print_exc()