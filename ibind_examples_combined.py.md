# IBind Examples - Combined
# Source: https://github.com/Voyz/ibind/tree/master/examples


################################################################################
# rest_01_basic.py
################################################################################

"""
REST basic.

Minimal example of using the IbkrClient class.
"""
```python
from ibind import IbkrClient

# Construct the client
client = IbkrClient()

# Call some endpoints
print('\n#### check_health ####')
print(client.check_health())

print('\n\n#### tickle ####')
print(client.tickle().data)

print('\n\n#### get_accounts ####')
print(client.portfolio_accounts().data)

```

################################################################################
# rest_02_intermediate.py
################################################################################

"""
REST Intermediate

In this example we:

* Initialise the IBind logs
* Provide a CAcert (assuming the Gateway is using the same one)
* Showcase several REST API calls

Assumes the Gateway is deployed at 'localhost:5000' and the IBIND_ACCOUNT_ID and IBIND_CACERT environment variables have been set.
"""
```python
import os

from ibind import IbkrClient, ibind_logs_initialize

ibind_logs_initialize()

cacert = os.getenv('IBIND_CACERT', False)  # insert your cacert path here
client = IbkrClient(cacert=cacert)

print('\n#### get_accounts ####')
accounts = client.portfolio_accounts().data
client.account_id = accounts[0]['accountId']
print(accounts)

print('\n\n#### get_ledger ####')
ledger = client.get_ledger().data
for currency, subledger in ledger.items():
    print(f'\t Ledger currency: {currency}')
    print(f'\t cash balance: {subledger["cashbalance"]}')
    print(f'\t net liquidation value: {subledger["netliquidationvalue"]}')
    print(f'\t stock market value: {subledger["stockmarketvalue"]}')
    print()

print('\n#### get_positions ####')
positions = client.positions().data
for position in positions:
    print(f'\t Position {position["ticker"]}: {position["position"]} (${position["mktValue"]})')

```

################################################################################
# rest_03_stock_querying.py
################################################################################

"""
REST Stock Querying

In this example we:

* Get stock security data by symbol
* Showcase using StockQuery class for advanced stock filtering
* Get conids by using StockQuery queries
* Showcase an error encountered when getting conids returns multiple contracts or instruments

Assumes the Gateway is deployed at 'localhost:5000' and the IBIND_ACCOUNT_ID and IBIND_CACERT environment variables have been set.
"""
```python
import os
from pprint import pprint

from ibind import IbkrClient, StockQuery, ibind_logs_initialize

ibind_logs_initialize(log_to_file=False)

cacert = os.getenv('IBIND_CACERT', False)  # insert your cacert path here
client = IbkrClient(cacert=cacert)


print('#### get_stocks ####')
stocks = client.security_stocks_by_symbol('AAPL').data
print(stocks)


print('\n#### get_conids ####')
conids = client.stock_conid_by_symbol('AAPL').data
print(conids)


print('\n#### using StockQuery ####')
conids = client.stock_conid_by_symbol(StockQuery('AAPL', contract_conditions={'exchange': 'MEXI'}), default_filtering=False).data
pprint(conids)


print('\n#### mixed queries ####')
stock_queries = [StockQuery('AAPL', contract_conditions={'exchange': 'MEXI'}), 'HUBS', StockQuery('GOOG', name_match='ALPHABET INC - CDR')]
conids = client.stock_conid_by_symbol(stock_queries, default_filtering=False).data
pprint(conids)


"""
    The get_conids() method will raise an exception if the filtered stocks response doesn't provide exactly one conid.
    The default_filtering filtered the returned contracts by isUS=True which usually returns only one conid.
    If multiple conids are found, you must provide additional conditions for the particular stock in order in order to ensure only one conid is returned.

    Uncomment the following lines to see the exception raised when multiple conids are returned.
"""
# print('\n#### get_conid with too many conids ####')
# conids = client.stock_conid_by_symbol('AAPL', default_filtering=False).data
# pprint(conids)

```

################################################################################
# rest_04_place_order.py
################################################################################

"""
REST Place Order

In this example we:

* Set up an order_request using make_order_request() method
* Prepare the place_order answers based on the QuestionType enum
* Mock the place_order endpoint to prevent submitting an actual order
* Call the place_order() method

Assumes the Gateway is deployed at 'localhost:5000' and the IBIND_ACCOUNT_ID and IBIND_CACERT environment variables have been set.
"""
```python
import datetime
import os
from unittest.mock import patch, MagicMock

from ibind import IbkrClient, QuestionType, ibind_logs_initialize
from ibind.client.ibkr_utils import OrderRequest

ibind_logs_initialize(log_to_file=False)

account_id = os.getenv('IBIND_ACCOUNT_ID', '[YOUR_ACCOUNT_ID]')
cacert = os.getenv('IBIND_CACERT', False)  # insert your cacert path here
client = IbkrClient(cacert=cacert, use_session=False)

conid = 265598
side = 'BUY'
size = 1
order_type = 'MKT'
order_tag = f'my_order-{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}'

order_request = OrderRequest(conid=conid, side=side, quantity=size, order_type=order_type, acct_id=account_id, coid=order_tag)

answers = {
    QuestionType.PRICE_PERCENTAGE_CONSTRAINT: True,
    QuestionType.ORDER_VALUE_LIMIT: True,
    'Unforeseen new question': True,
}

mocked_responses = [
    [{'id': 0, 'message': ['price exceeds the Percentage constraint of 3%.']}],
    [{'id': 1, 'message': ['exceeds the Total Value Limit of']}],
    [{'success': True}],
]

print('#### submit_order ####')

# We mock the requests module to prevent submitting orders in this example script.
# Comment out the next two lines if you'd like to actually submit the orders to IBKR.
with patch('ibind.base.rest_client.requests') as requests_mock:
    requests_mock.request.return_value = MagicMock(json=MagicMock(side_effect=mocked_responses))

    response = client.place_order(order_request, answers, account_id).data

print(response)


```
################################################################################
# rest_05_marketdata_history.py
################################################################################

"""
REST Market Data History

In this example we:

* Query historical market data by conid
* Query historical market data by symbol
* Showcase using the marketdata_history_by_symbols to query one and multiple symbols
* Showcase the time difference between these various calls

Assumes the Gateway is deployed at 'localhost:5000' and the IBIND_ACCOUNT_ID and IBIND_CACERT environment variables have been set.
"""
```python
import os
import time

from ibind import IbkrClient, ibind_logs_initialize

ibind_logs_initialize(log_to_file=False)

cacert = os.getenv('IBIND_CACERT', False)  # insert your cacert path here
client = IbkrClient(cacert=cacert, timeout=2)

st = time.time()
history = client.marketdata_history_by_conid('265598', period='1d', bar='1d', outside_rth=True)
diff_one_conid = time.time() - st
print('#### One conid ####')
print(f'{history}')

st = time.time()
history = client.marketdata_history_by_symbol('AAPL', period='1d', bar='1d', outside_rth=True)
diff_one_symbol_raw = time.time() - st
print('\n\n#### One symbol raw ####')
print(f'{history}')

st = time.time()
history = client.marketdata_history_by_symbols('AAPL', period='1d', bar='1d', outside_rth=True)
diff_one_symbol = time.time() - st
print('\n\n#### One symbol ####')
print(f'{history}')

st = time.time()
history_sync = client.marketdata_history_by_symbols(
    ['AAPL', 'MSFT', 'GOOG', 'TSLA', 'AMZN'], period='1d', bar='1d', outside_rth=True, run_in_parallel=False
)
diff_five_symbols_sync = time.time() - st
print('\n\n#### Five symbols synchronous ####')
print(f'{history_sync}')


st = time.time()
history = client.marketdata_history_by_symbols(['AAPL', 'MSFT', 'GOOG', 'TSLA', 'AMZN'], period='1d', bar='1d', outside_rth=True)
diff_five_symbols = time.time() - st
print('\n\n#### Five symbols parallel ####')
print(f'{history}')

time.sleep(5)
st = time.time()
history = client.marketdata_history_by_symbols(
    ['AAPL', 'MSFT', 'GOOG', 'TSLA', 'AMZN', 'ADBE', 'AMD', 'COIN', 'META', 'DIS', 'BAC', 'XOM', 'KO', 'WMT', 'V'],
    period='1d',
    bar='1d',
    outside_rth=True,
)
diff_fifteen_symbols = time.time() - st
print('\n\n#### Fifteen symbols ####')
print(f'{history}')

print(f'\n\n1 conid took: {diff_one_conid:.2f}s')
print(f'1 symbol raw took: {diff_one_symbol_raw:.2f}s')
print(f'1 symbol took: {diff_one_symbol:.2f}s')
print(f'5 symbols sync took: {diff_five_symbols_sync:.2f}s')
print(f'5 symbols took: {diff_five_symbols:.2f}s')
print(f'15 symbols took: {diff_fifteen_symbols:.2f}s')

```

################################################################################
# rest_06_options_chain.py
################################################################################
```python
"""
REST options chain

In this example we:

* Retrieve an options chain for the S&P 500 index
* Submit a spread order for two of its strikes

Assumes the Gateway is deployed at 'localhost:5000' and the IBIND_ACCOUNT_ID and IBIND_CACERT environment variables have been set.
"""
import datetime
import os
from pprint import pprint
from unittest.mock import patch, MagicMock

from ibind import IbkrClient, ibind_logs_initialize, OrderRequest, QuestionType
from ibind.support.py_utils import print_table

ibind_logs_initialize()

cacert = os.getenv('IBIND_CACERT', False)  # insert your cacert path here
client = IbkrClient(cacert=cacert, use_session=False)


###################################
#### LOOKING UP OPTIONS CHAINS ####
###################################

print('\n#### search for contract ####')
contracts = client.search_contract_by_symbol('SPX').data
spx_contract = contracts[0]
pprint(spx_contract)

# find the options section in spx_contract
options = None
for section in spx_contract['sections']:
    if section['secType'] == 'OPT':
        options = section
        break

if options is None:
    raise RuntimeError(f'No options found in spx_contract: {spx_contract}')

options['months'] = options['months'].split(';')
options['exchange'] = options['exchange'].split(';')

print('\n#### search for strikes ####')
strikes = client.search_strikes_by_conid(conid=spx_contract['conid'], sec_type='OPT', month=options['months'][0]).data
print(str(strikes).replace("'put'", "\n'put'"))

print('\n#### validate contract ####')
info = client.search_secdef_info_by_conid(
    conid=spx_contract['conid'], sec_type='OPT', month=options['months'][0], strike=strikes['call'][0], right='C'
).data

print_table(info)


#########################################
#### SUBMITTING OPTIONS SPREAD ORDER ####
#########################################

account_id = os.getenv('IBIND_ACCOUNT_ID', '[YOUR_ACCOUNT_ID]')
currency = 'USD'

# Configure the legs as needed
legs = [
    {'conid': info[0]['conid'], 'ratio': 1, 'side': 'BUY'},
    {'conid': info[1]['conid'], 'ratio': 1, 'side': 'SELL'},
]

# Look this up in the documentation to verify these conids are correct
_SPREAD_CONIDS = {
    'AUD': '61227077',
    'CAD': '61227082',
    'CHF': '61227087',
    'CNH': '136000441',
    'GBP': '58666491',
    'HKD': '61227072',
    'INR': '136000444',
    'JPY': '61227069',
    'KRW': '136000424',
    'MXN': '136000449',
    'SEK': '136000429',
    'SGD': '426116555',
    'USD': '28812380',
}

# Build conidex string for combo order
# Combo Orders follow the format of: '{spread_conid};;;{leg_conid1}/{ratio},{leg_conid2}/{ratio}'
conidex = f"{_SPREAD_CONIDS[currency]};;;"

leg_strings = []
for leg in legs:
    multiplier = 1 if leg['side'] == "BUY" else -1
    leg_string = f'{leg['conid']}/{leg['ratio'] * multiplier}'
    leg_strings.append(leg_string)

conidex = conidex + ",".join(leg_strings)

# Prepare the OrderRequest
side = 'BUY'
size = 1
order_type = 'MKT'
order_tag = f'my_order-{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}'

order_request = OrderRequest(
    conid=None, # must be None when specifying conidex
    conidex=conidex,
    side=side,
    quantity=size,
    order_type=order_type,
    acct_id=account_id,
    coid=order_tag
)

answers = {
    QuestionType.PRICE_PERCENTAGE_CONSTRAINT: True,
    # ...
}

print('\n#### Submitting spread order ####')
print(f'conidex:\n{conidex}')

# We mock the requests module to prevent submitting orders in this example script.
# Comment out the next two lines if you'd like to actually submit the orders to IBKR.
with patch('ibind.base.rest_client.requests') as requests_mock:
    requests_mock.request.return_value = MagicMock(json=MagicMock(side_effect=[[{'success': True}]]))

    response = client.place_order(order_request, answers, account_id).data

print(response)

```

################################################################################
# rest_07_bracket_orders.py
################################################################################

"""
REST Bracket Orders

In this example we:

* Set up the bracket order request dicts using make_order_request() method
* Prepare the place_order answers based on the QuestionType enum
* Submit the bracket orders

Assumes the Gateway is deployed at 'localhost:5000' and the IBIND_ACCOUNT_ID and IBIND_CACERT environment variables have been set.
"""
```python
import datetime
import os
from functools import partial

from ibind import IbkrClient, make_order_request, QuestionType, ibind_logs_initialize

ibind_logs_initialize(log_to_file=False)

account_id = os.getenv('IBIND_ACCOUNT_ID', '[YOUR_ACCOUNT_ID]')
cacert = os.getenv('IBIND_CACERT', False)  # insert your cacert path here
client = IbkrClient(cacert=cacert)

conid = '265598'
price = 211.07
order_tag = f'my_order-{datetime.datetime.now().strftime("%Y%m%d%H%M%S")}'

order_request_partial = partial(make_order_request, conid=conid, acct_id=account_id, quantity=1)

parent = order_request_partial(side='BUY', order_type='LMT', price=price, coid=order_tag)
stop_loss = order_request_partial(side='SELL', order_type='STP', price=price - 1, parent_id=order_tag)
take_profit = order_request_partial(side='SELL', order_type='LMT', price=price + 1, parent_id=order_tag)

requests = [parent, stop_loss, take_profit]

answers = {
    QuestionType.PRICE_PERCENTAGE_CONSTRAINT: True,
    QuestionType.ORDER_VALUE_LIMIT: True,
    QuestionType.MISSING_MARKET_DATA: True,
    QuestionType.STOP_ORDER_RISKS: True,
}

print('#### submit_order ####')

response = client.place_order(requests, answers, account_id).data

print(response)


```
################################################################################
# rest_08_oauth.py
################################################################################

"""
REST OAuth.

Showcases usage of OAuth 1.0a with IbkrClient.

This example is equivalent to rest_02_intermediate.py, except that it uses OAuth 1.0a for authentication.

Using IbkrClient with OAuth 1.0a support will automatically handle generating the OAuth live session token and tickling the connection to maintain it active. You should be able to use all endpoints in the same way as when not using OAuth.

Importantly, in order to use OAuth 1.0a you're required to set up the following environment variables:

- IBIND_USE_OAUTH: Set to True.
- IBIND_OAUTH1A_ACCESS_TOKEN: OAuth access token generated in the self-service portal.
- IBIND_OAUTH1A_ACCESS_TOKEN_SECRET: OAuth access token secret generated in the self-service portal.
- IBIND_OAUTH1A_CONSUMER_KEY: The consumer key configured during the onboarding process. This uniquely identifies the project in the IBKR ecosystem.
- IBIND_OAUTH1A_DH_PRIME: The hex representation of the Diffie-Hellman prime.
- IBIND_OAUTH1A_ENCRYPTION_KEY_FP: The path to the private OAuth encryption key.
- IBIND_OAUTH1A_SIGNATURE_KEY_FP: The path to the private OAuth signature key.

Optionally, you can also set:
- IBIND_OAUTH1A_REALM: OAuth connection type. This is generally set to "limited_poa", however should be set to "test_realm" when using the TESTCONS consumer key. (optional, defaults to "limited_poa")
- IBIND_OAUTH1A_DH_GENERATOR: The Diffie-Hellman generator value (optional, defaults to 2).

If you prefer setting these variables inline, you can pass an instance of OAuth1aConfig class as an optional 'oauth_config' parameter to the IbkrClient constructor. Any variables not specified will be taken from the environment variables.
"""
```python
import os

from ibind import IbkrClient, ibind_logs_initialize

ibind_logs_initialize()

cacert = os.getenv('IBIND_CACERT', False)  # insert your cacert path here

client = IbkrClient(
    cacert=cacert,
    use_oauth=True,
    # Optionally, specify OAuth variables dynamically by passing an OAuth1aConfig instance
    # oauth_config=OAuth1aConfig(access_token='my_access_token', access_token_secret='my_access_token_secret')
)

print('\n#### get_accounts ####')
accounts = client.portfolio_accounts().data
client.account_id = accounts[0]['accountId']
print(accounts)

print('\n\n#### get_ledger ####')
ledger = client.get_ledger().data
for currency, subledger in ledger.items():
    print(f'\t Ledger currency: {currency}')
    print(f'\t cash balance: {subledger["cashbalance"]}')
    print(f'\t net liquidation value: {subledger["netliquidationvalue"]}')
    print(f'\t stock market value: {subledger["stockmarketvalue"]}')
    print()

print('\n#### get_positions ####')
positions = client.positions().data
for position in positions:
    print(f'\t Position {position["ticker"]}: {position["position"]} (${position["mktValue"]})')

```

################################################################################
# ws_01_basic.py
################################################################################

"""
WebSocket Basic

In this example we:

* Demonstrate the basic usage of the IbkrWsClient
* Select the PNL WebSocket channel
* Subscribe to the PNL channel
* Wait for a new item. If there are no PnL reports there will be no data printed.

Assumes the Gateway is deployed at 'localhost:5000' and the IBIND_ACCOUNT_ID and IBIND_CACERT environment variables have been set.
"""
```python
from ibind import IbkrWsKey, IbkrWsClient

# Construct the client. Assumes IBIND_ACCOUNT_ID and IBIND_CACERT environment variables have been set.
ws_client = IbkrWsClient(start=True)

# Choose the WebSocket channel
ibkr_ws_key = IbkrWsKey.PNL

# Subscribe to the PNL channel
ws_client.subscribe(channel=ibkr_ws_key.channel)

# Wait for new items in the PNL queue.
while True:
    while not ws_client.empty(ibkr_ws_key):
        print(ws_client.get(ibkr_ws_key))

```

################################################################################
# ws_02_intermediate.py
################################################################################

"""
WebSocket Intermediate

In this example we:

* Demonstrate subscription to multiple channels
* Utilise queue accessors
* Use the 'signal' module to ensure we unsubscribe and shutdown upon the program termination

Assumes the Gateway is deployed at 'localhost:5000' and the IBIND_ACCOUNT_ID and IBIND_CACERT environment variables have been set.
"""
```python
import os
import signal
import time

from ibind import IbkrWsKey, IbkrWsClient, ibind_logs_initialize

ibind_logs_initialize(log_to_file=False)

account_id = os.getenv('IBIND_ACCOUNT_ID', '[YOUR_ACCOUNT_ID]')
cacert = os.getenv('IBIND_CACERT', False)  # insert your cacert path here

ws_client = IbkrWsClient(cacert=cacert, account_id=account_id)

ws_client.start()

requests = [
    {'channel': 'md+265598', 'data': {'fields': ['55', '71', '84', '86', '88', '85', '87', '7295', '7296', '70']}},
    {'channel': 'or'},
    {'channel': 'tr'},
    {'channel': f'sd+{account_id}'},
    {'channel': f'ld+{account_id}'},
    {'channel': 'pl'},
]
queue_accessors = [
    ws_client.new_queue_accessor(IbkrWsKey.TRADES),
    ws_client.new_queue_accessor(IbkrWsKey.MARKET_DATA),
    ws_client.new_queue_accessor(IbkrWsKey.ORDERS),
    ws_client.new_queue_accessor(IbkrWsKey.ACCOUNT_SUMMARY),
    ws_client.new_queue_accessor(IbkrWsKey.ACCOUNT_LEDGER),
    ws_client.new_queue_accessor(IbkrWsKey.PNL),
]


def stop(_, _1):
    for request in requests:
        ws_client.unsubscribe(**request)

    ws_client.shutdown()


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)

for request in requests:
    while not ws_client.subscribe(**request):
        time.sleep(1)

while ws_client.running:
    try:
        for qa in queue_accessors:
            while not qa.empty():
                print(str(qa), qa.get())

        time.sleep(1)
    except KeyboardInterrupt:
        print('KeyboardInterrupt')
        break

stop(None, None)

```

################################################################################
# ws_03_market_history.py
################################################################################

"""
WebSocket Market Data History

In this example we:

* Create a custom SubscriptionProcessor that overrides the default make_unsubscribe_payload method to use the server id instead of the conid
* Use a custom unsubscribe method to iterate over all server ids for market history and attempt to unsubscribe
* Demonstrate using the Market Data History channel
* Use the 'signal' module to ensure we unsubscribe and shutdown upon the program termination

Assumes the Gateway is deployed at 'localhost:5000' and the IBIND_ACCOUNT_ID and IBIND_CACERT environment variables have been set.
"""
```python
import os
import signal
import time

from ibind import IbkrSubscriptionProcessor, IbkrWsKey, IbkrWsClient, ibind_logs_initialize

ibind_logs_initialize(log_to_file=False)

cacert = os.getenv('IBIND_CACERT', False)  # insert your cacert path here

ws_client = IbkrWsClient(cacert=cacert)


# override the default subscription processor since we need to use the server id instead of conid
class MhSubscriptionProcessor(IbkrSubscriptionProcessor):  # pragma: no cover
    def make_unsubscribe_payload(self, channel: str, server_id: dict = None) -> str:
        return f'umh+{server_id}'


subscription_processor = MhSubscriptionProcessor()


def unsubscribe():
    # loop all server ids for market history and attempt to unsubscribe
    for server_id, conid in ws_client.server_ids(IbkrWsKey.MARKET_HISTORY).items():
        channel = 'mh'
        needs_confirmation = False

        if conid is not None:  # if we know the conid let's try to confirm the unsubscription
            channel += f'+{conid}'
            needs_confirmation = True

        confirmed = ws_client.unsubscribe(channel, server_id, needs_confirmation, subscription_processor)

        print(f'Unsubscribing channel {channel!r} from server {server_id!r}: {"unconfirmed" if not confirmed else "confirmed"}.')


request = {'channel': 'mh+265598', 'data': {'period': '1min', 'bar': '1min', 'outsideRTH': True, 'source': 'trades', 'format': '%o/%c/%h/%l'}}

ws_client.start()

qa = ws_client.new_queue_accessor(IbkrWsKey.MARKET_HISTORY)


def stop(_, _1):
    unsubscribe()
    ws_client.shutdown()


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)

while not ws_client.subscribe(**request):
    time.sleep(1)

while ws_client.running:
    try:
        while not qa.empty():
            print(str(qa), qa.get())

        time.sleep(1)
    except KeyboardInterrupt:
        print('KeyboardInterrupt')
        break

ws_client.shutdown()
```

