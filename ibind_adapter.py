"""
IBind Trading Wrapper - COMPLETE VERSION
Automatizált trading Interactive Brokers-en keresztül

Használat:
    from ib_trading_client import IBTradingClient, OrderSide, OrderType, OptionRight

    client = IBTradingClient(account_id='DU123456')

    # Stock order
    response = client.place_stock_order('AAPL', OrderSide.BUY, 10)

    # Option order
    response = client.place_option_order(
        symbol='SPX',
        strike=5800,
        right=OptionRight.CALL,
        expiry_month='DEC24',
        side=OrderSide.BUY,
        quantity=1
    )

    # Spread order (Iron Condor, Credit Spread, stb.)
    response = client.place_option_spread_order(
        legs=[
            {'conid': 123456, 'ratio': 1, 'side': 'BUY'},
            {'conid': 123457, 'ratio': 1, 'side': 'SELL'},
        ],
        side=OrderSide.BUY,
        quantity=1
    )

    # Order tracking
    orders = client.get_live_orders()
    history = client.get_order_history(days=7)
    trades = client.get_trades(days=7)
"""

import os
import time
import logging
from typing import List, Dict, Optional, Union, Tuple
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from ibind import (
    IbkrClient,
    IbkrWsClient,
    IbkrWsKey,
    QuestionType,
    ibind_logs_initialize,
    StockQuery
)
from ibind.client.ibkr_utils import make_order_request


# ===== ENUMS =====

class OrderSide(Enum):
    """Order irányok"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """Order típusok"""
    MARKET = "MKT"
    LIMIT = "LMT"
    STOP = "STP"
    STOP_LIMIT = "STP_LMT"


class OptionRight(Enum):
    """Opció típusok"""
    CALL = "C"
    PUT = "P"


class OrderStatus(Enum):
    """Order státuszok"""
    SUBMITTED = "Submitted"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    PENDING_SUBMIT = "PendingSubmit"
    PENDING_CANCEL = "PendingCancel"
    PRE_SUBMITTED = "PreSubmitted"
    INACTIVE = "Inactive"
    REJECTED = "Rejected"


# ===== DATACLASSES =====

@dataclass
class Position:
    """Pozíció adatok"""
    ticker: str
    quantity: float
    market_value: float
    avg_price: float
    unrealized_pnl: float
    conid: int
    account: str
    raw_data: Dict


@dataclass
class OrderResponse:
    """Order válasz"""
    success: bool
    order_id: Optional[str]
    message: Optional[str]
    raw_response: Dict


@dataclass
class OrderInfo:
    """Order információ"""
    order_id: str
    account: str
    symbol: str
    conid: int
    side: str
    order_type: str
    quantity: float
    filled_quantity: float
    remaining_quantity: float
    price: Optional[float]
    avg_fill_price: Optional[float]
    status: str
    time_submitted: Optional[str]
    time_updated: Optional[str]
    commission: Optional[float]
    text: Optional[str]
    raw_data: Dict


@dataclass
class Trade:
    """Executed trade (fill)"""
    execution_id: str
    order_id: str
    symbol: str
    conid: int
    side: str
    quantity: float
    price: float
    time: str
    commission: Optional[float]
    account: str
    raw_data: Dict


@dataclass
class OptionChainInfo:
    """Opciós chain információ"""
    underlying_conid: int
    underlying_symbol: str
    available_months: List[str]
    selected_month: str
    call_strikes: List[float]
    put_strikes: List[float]
    raw_data: Dict


@dataclass
class OptionContractInfo:
    """Konkrét option contract info"""
    conid: int
    symbol: str
    strike: float
    right: str  # 'C' vagy 'P'
    expiry: str
    multiplier: int
    exchange: str
    raw_data: Dict


# ===== SPREAD CONID MAPPING =====

# Ezek az IBKR hivatalos spread conid-jai currency szerint
# Forrás: IBKR API dokumentáció
SPREAD_CONIDS = {
    'USD': '28812380',
    'EUR': '28812432',
    'GBP': '58666491',
    'CHF': '61227087',
    'JPY': '61227069',
    'CAD': '61227082',
    'AUD': '61227077',
    'HKD': '61227072',
    'SEK': '136000429',
    'SGD': '426116555',
    'MXN': '136000449',
    'KRW': '136000424',
    'INR': '136000444',
    'CNH': '136000441',
}


# ===== MAIN CLIENT =====

class IBTradingClient:
    """
    IBind wrapper teljes funkcionalitással.

    Features:
    - Connection & health check
    - Account info & positions
    - Stock & option orders
    - Option spread orders (combo orders)
    - Order tracking & history
    - Market data (historical & real-time)
    - WebSocket support
    """

    def __init__(
            self,
            account_id: Optional[str] = None,
            base_url: str = 'https://localhost:5000',
            cacert: Optional[str] = None,
            timeout: int = 10,
            auto_confirm_orders: bool = True,
            log_level: str = 'INFO',
            use_oauth: bool = False,
            oauth_config: Optional[Dict] = None
    ):
        """
        Inicializálás

        Args:
            account_id: IB account ID (vagy IBIND_ACCOUNT_ID env var)
            base_url: Gateway URL
            cacert: CA certificate path (vagy IBIND_CACERT env var)
            timeout: Request timeout
            auto_confirm_orders: Automatikusan confirmálja az ordereket
            log_level: Logging szint
            use_oauth: OAuth 1.0a használata
            oauth_config: OAuth config dict (ha use_oauth=True)
        """
        # Env vars
        self.account_id = account_id or os.getenv('IBIND_ACCOUNT_ID')
        if not self.account_id:
            raise ValueError("Account ID must be provided or set in IBIND_ACCOUNT_ID env var")

        cacert = cacert or os.getenv('IBIND_CACERT')

        # Logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(handler)

        # IBind logs
        ibind_logs_initialize(log_to_file=False)

        # REST client
        client_kwargs = {
            'url': base_url,
            'cacert': cacert,
            'timeout': timeout,
            'account_id': self.account_id,
            'use_oauth': use_oauth,
        }

        if oauth_config:
            client_kwargs['oauth_config'] = oauth_config

        self.client = IbkrClient(**client_kwargs)

        # WebSocket client (lazy init)
        self._ws_client: Optional[IbkrWsClient] = None
        self._cacert = cacert

        # Order confirmation
        self.auto_confirm_orders = auto_confirm_orders
        self.default_answers = {
            QuestionType.PRICE_PERCENTAGE_CONSTRAINT: True,
            QuestionType.ORDER_VALUE_LIMIT: True,
            QuestionType.MISSING_MARKET_DATA: True,
            QuestionType.STOP_ORDER_RISKS: True,
        }

        self.logger.info(f"IBTradingClient initialized for account {self.account_id}")

    # ===== CONNECTION & HEALTH =====

    def check_connection(self) -> bool:
        """Gateway kapcsolat ellenőrzése"""
        try:
            health = self.client.check_health()
            self.logger.info(f"Gateway health check: {health}")
            return True
        except Exception as e:
            self.logger.error(f"Gateway health check failed: {e}")
            return False

    def tickle(self) -> Dict:
        """Session fenntartása"""
        return self.client.tickle().data

    # ===== ACCOUNT INFO =====

    def get_accounts(self) -> List[Dict]:
        """Account lista"""
        return self.client.portfolio_accounts().data

    def get_account_balance(self) -> Dict[str, Dict[str, float]]:
        """
        Account balance és margin info

        Returns:
            Dict[currency] -> {cash_balance, net_liquidation, stock_market_value}
        """
        ledger = self.client.get_ledger().data

        result = {}
        for currency, subledger in ledger.items():
            result[currency] = {
                'cash_balance': float(subledger.get('cashbalance', 0)),
                'net_liquidation': float(subledger.get('netliquidationvalue', 0)),
                'stock_market_value': float(subledger.get('stockmarketvalue', 0)),
            }

        return result

    def get_positions(self) -> List[Position]:
        """
        Összes pozíció lekérése

        Returns:
            Lista Position objektumokkal
        """
        positions_raw = self.client.positions().data

        positions = []
        for pos in positions_raw:
            positions.append(Position(
                ticker=pos.get('ticker', ''),
                quantity=float(pos.get('position', 0)),
                market_value=float(pos.get('mktValue', 0)),
                avg_price=float(pos.get('avgPrice', 0)),
                unrealized_pnl=float(pos.get('unrealizedPnL', 0)),
                conid=int(pos.get('conid', 0)),
                account=pos.get('acctId', self.account_id),
                raw_data=pos
            ))

        return positions

    def get_position_by_symbol(self, symbol: str) -> Optional[Position]:
        """Konkrét symbol pozíciójának lekérése"""
        positions = self.get_positions()
        for pos in positions:
            if pos.ticker == symbol:
                return pos
        return None

    # ===== SYMBOL & CONTRACT LOOKUP =====

    def get_stock_conid(
            self,
            symbol: str,
            exchange: Optional[str] = None,
            currency: Optional[str] = None
    ) -> int:
        """
        Stock contract ID (conid) lekérése

        Args:
            symbol: Ticker symbol
            exchange: Opcionális exchange filter (pl. 'NASDAQ', 'NYSE')
            currency: Opcionális currency filter (pl. 'USD')

        Returns:
            Contract ID
        """
        try:
            if exchange or currency:
                # Advanced filtering
                conditions = {}
                if exchange:
                    conditions['exchange'] = exchange
                if currency:
                    conditions['currency'] = currency

                query = StockQuery(symbol, contract_conditions=conditions)
                conid = self.client.stock_conid_by_symbol(query, default_filtering=False).data
            else:
                # Simple lookup
                conid = self.client.stock_conid_by_symbol(symbol).data

            self.logger.info(f"Got conid for {symbol}: {conid}")
            return conid

        except Exception as e:
            self.logger.error(f"Failed to get conid for {symbol}: {e}")
            raise

    def search_option_chain(
            self,
            symbol: str,
            expiry_month: Optional[str] = None
    ) -> OptionChainInfo:
        """
        Opciós chain lekérése

        Args:
            symbol: Underlying symbol
            expiry_month: Hónap (pl. 'DEC24'), None = első elérhető

        Returns:
            OptionChainInfo object
        """
        # Contract keresés
        contracts = self.client.search_contract_by_symbol(symbol).data
        if not contracts:
            raise ValueError(f"No contract found for symbol: {symbol}")

        contract = contracts[0]
        conid = contract['conid']

        # Options section
        options = None
        for section in contract.get('sections', []):
            if section['secType'] == 'OPT':
                options = section
                break

        if not options:
            raise ValueError(f"No options found for symbol: {symbol}")

        months = options['months'].split(';')
        month = expiry_month or months[0]

        # Strikes lekérése
        strikes = self.client.search_strikes_by_conid(
            conid=conid,
            sec_type='OPT',
            month=month
        ).data

        return OptionChainInfo(
            underlying_conid=conid,
            underlying_symbol=symbol,
            available_months=months,
            selected_month=month,
            call_strikes=strikes.get('call', []),
            put_strikes=strikes.get('put', []),
            raw_data=strikes
        )

    def get_option_contract_info(
            self,
            symbol: str,
            strike: float,
            right: Union[str, OptionRight],
            expiry_month: str
    ) -> List[OptionContractInfo]:
        """
        Konkrét option contract info

        Args:
            symbol: Underlying
            strike: Strike price
            right: 'C' vagy 'P'
            expiry_month: Lejárati hónap

        Returns:
            Lista OptionContractInfo objektumokkal
        """
        if isinstance(right, OptionRight):
            right = right.value

        # Underlying conid
        contracts = self.client.search_contract_by_symbol(symbol).data
        conid = contracts[0]['conid']

        # Contract info
        info_list = self.client.search_secdef_info_by_conid(
            conid=conid,
            sec_type='OPT',
            month=expiry_month,
            strike=strike,
            right=right
        ).data

        result = []
        for info in info_list:
            result.append(OptionContractInfo(
                conid=info['conid'],
                symbol=info.get('ticker', ''),
                strike=float(info.get('strike', strike)),
                right=info.get('right', right),
                expiry=info.get('maturityDate', ''),
                multiplier=int(info.get('multiplier', 100)),
                exchange=info.get('exchange', ''),
                raw_data=info
            ))

        return result

    # ===== MARKET DATA =====

    def get_market_data_history(
            self,
            symbols: Union[str, List[str]],
            period: str = '1d',
            bar: str = '5min',
            outside_rth: bool = True,
            parallel: bool = True
    ) -> Dict[str, List[Dict]]:
        """
        Historical market data

        Args:
            symbols: Egy symbol vagy lista
            period: Időszak ('1d', '1w', '1m')
            bar: Bar size ('1min', '5min', '1h', '1d')
            outside_rth: Outside regular trading hours
            parallel: Párhuzamos lekérés (több symbol esetén)

        Returns:
            Dict[symbol] -> history data
        """
        if isinstance(symbols, str):
            symbols = [symbols]

        history = self.client.marketdata_history_by_symbols(
            symbols,
            period=period,
            bar=bar,
            outside_rth=outside_rth,
            run_in_parallel=parallel
        )

        return history

    # ===== ORDER PLACEMENT - STOCKS =====

    def place_stock_order(
            self,
            symbol: str,
            side: Union[str, OrderSide],
            quantity: int,
            order_type: Union[str, OrderType] = OrderType.MARKET,
            limit_price: Optional[float] = None,
            stop_price: Optional[float] = None,
            tag: Optional[str] = None,
            exchange: Optional[str] = None
    ) -> OrderResponse:
        """
        Stock order

        Args:
            symbol: Ticker
            side: 'BUY' vagy 'SELL'
            quantity: Mennyiség
            order_type: Order típus
            limit_price: Limit ár
            stop_price: Stop ár
            tag: Custom tag
            exchange: Exchange filter

        Returns:
            OrderResponse
        """
        # Enum conversions
        if isinstance(side, OrderSide):
            side = side.value
        if isinstance(order_type, OrderType):
            order_type = order_type.value

        # Conid
        conid = self.get_stock_conid(symbol, exchange=exchange)

        # Tag
        if not tag:
            tag = f"{symbol}_{side}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Order request
        order_kwargs = {
            'conid': conid,
            'side': side,
            'quantity': quantity,
            'order_type': order_type,
            'acct_id': self.account_id,
            'coid': tag
        }

        if limit_price:
            order_kwargs['price'] = limit_price
        if stop_price:
            order_kwargs['stop_price'] = stop_price

        order_request = make_order_request(**order_kwargs)

        # Execute
        try:
            response = self.client.place_order(
                order_request,
                self.default_answers,
                self.account_id
            ).data

            success = self._extract_success(response)
            order_id = self._extract_order_id(response)

            self.logger.info(
                f"Stock order placed: {symbol} {side} {quantity} @ {order_type} - Success: {success}, ID: {order_id}")

            return OrderResponse(
                success=success,
                order_id=order_id,
                message=None,
                raw_response=response
            )

        except Exception as e:
            self.logger.error(f"Stock order failed: {e}")
            return OrderResponse(
                success=False,
                order_id=None,
                message=str(e),
                raw_response={}
            )

    # ===== ORDER PLACEMENT - OPTIONS =====

    def place_option_order(
            self,
            symbol: str,
            strike: float,
            right: Union[str, OptionRight],
            expiry_month: str,
            side: Union[str, OrderSide],
            quantity: int,
            order_type: Union[str, OrderType] = OrderType.MARKET,
            limit_price: Optional[float] = None,
            tag: Optional[str] = None
    ) -> OrderResponse:
        """
        Opció order

        Args:
            symbol: Underlying
            strike: Strike price
            right: 'C' vagy 'P'
            expiry_month: Lejárat (pl. 'DEC24')
            side: 'BUY' vagy 'SELL'
            quantity: Mennyiség
            order_type: Order típus
            limit_price: Limit ár
            tag: Custom tag

        Returns:
            OrderResponse
        """
        # Conversions
        if isinstance(side, OrderSide):
            side = side.value
        if isinstance(right, OptionRight):
            right = right.value
        if isinstance(order_type, OrderType):
            order_type = order_type.value

        # Contract info
        contracts = self.get_option_contract_info(symbol, strike, right, expiry_month)

        if not contracts:
            raise ValueError(f"No contract found for {symbol} {strike}{right} {expiry_month}")

        conid = contracts[0].conid

        # Tag
        if not tag:
            tag = f"{symbol}_{strike}{right}_{side}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Order request
        order_kwargs = {
            'conid': conid,
            'side': side,
            'quantity': quantity,
            'order_type': order_type,
            'acct_id': self.account_id,
            'coid': tag
        }

        if limit_price:
            order_kwargs['price'] = limit_price

        order_request = make_order_request(**order_kwargs)

        # Execute
        try:
            response = self.client.place_order(
                order_request,
                self.default_answers,
                self.account_id
            ).data

            success = self._extract_success(response)
            order_id = self._extract_order_id(response)

            self.logger.info(f"Option order placed: {symbol} {strike}{right} {side} {quantity} - Success: {success}")

            return OrderResponse(
                success=success,
                order_id=order_id,
                message=None,
                raw_response=response
            )

        except Exception as e:
            self.logger.error(f"Option order failed: {e}")
            return OrderResponse(
                success=False,
                order_id=None,
                message=str(e),
                raw_response={}
            )

    # ===== ORDER PLACEMENT - SPREADS (COMBO ORDERS) =====

    def place_option_spread_order(
            self,
            legs: List[Dict[str, Union[int, str]]],
            side: Union[str, OrderSide],
            quantity: int,
            order_type: Union[str, OrderType] = OrderType.MARKET,
            limit_price: Optional[float] = None,
            currency: str = 'USD',
            tag: Optional[str] = None
    ) -> OrderResponse:
        """
        Option spread order (combo order) - Iron Condor, Credit Spread, stb.

        Ez EGY darab natív IBKR combo order, nem több külön order!

        Args:
            legs: Lista a spread leg-ekről
                  [{'conid': 123456, 'ratio': 1, 'side': 'BUY'},
                   {'conid': 123457, 'ratio': 1, 'side': 'SELL'}, ...]
            side: 'BUY' vagy 'SELL' (az egész spread-re)
            quantity: Hány spread contract
            order_type: 'MKT', 'LMT', stb.
            limit_price: Net credit/debit limit (ha LMT)
            currency: 'USD', 'EUR', stb.
            tag: Custom tag

        Returns:
            OrderResponse

        Példa Iron Condor:
            legs = [
                {'conid': 123, 'ratio': 1, 'side': 'BUY'},   # Long Put (lower)
                {'conid': 124, 'ratio': 1, 'side': 'SELL'},  # Short Put
                {'conid': 125, 'ratio': 1, 'side': 'SELL'},  # Short Call
                {'conid': 126, 'ratio': 1, 'side': 'BUY'},   # Long Call (higher)
            ]
            client.place_option_spread_order(legs, 'BUY', 1, limit_price=1.50)
        """
        # Conversions
        if isinstance(side, OrderSide):
            side = side.value
        if isinstance(order_type, OrderType):
            order_type = order_type.value

        # Spread conid
        spread_conid = SPREAD_CONIDS.get(currency)
        if not spread_conid:
            raise ValueError(f"Unknown currency: {currency}. Supported: {list(SPREAD_CONIDS.keys())}")

        # Conidex string építése
        leg_strings = []
        for leg in legs:
            leg_conid = leg['conid']
            leg_ratio = leg.get('ratio', 1)
            leg_side = leg['side']

            # Multiplier: BUY = +1, SELL = -1
            multiplier = 1 if leg_side == 'BUY' else -1
            leg_string = f"{leg_conid}/{leg_ratio * multiplier}"
            leg_strings.append(leg_string)

        conidex = f"{spread_conid};;;" + ",".join(leg_strings)

        # Tag
        if not tag:
            tag = f"spread_{len(legs)}leg_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Order request
        order_kwargs = {
            'conid': None,  # ❗ MUST be None for spread orders!
            'conidex': conidex,
            'side': side,
            'quantity': quantity,
            'order_type': order_type,
            'acct_id': self.account_id,
            'coid': tag
        }

        if limit_price:
            order_kwargs['price'] = limit_price

        order_request = make_order_request(**order_kwargs)

        # Execute
        try:
            response = self.client.place_order(
                order_request,
                self.default_answers,
                self.account_id
            ).data

            success = self._extract_success(response)
            order_id = self._extract_order_id(response)

            self.logger.info(f"Spread order placed: {len(legs)}-leg spread {side} {quantity} - Success: {success}")
            self.logger.debug(f"Conidex: {conidex}")

            return OrderResponse(
                success=success,
                order_id=order_id,
                message=f"{len(legs)}-leg spread",
                raw_response=response
            )

        except Exception as e:
            self.logger.error(f"Spread order failed: {e}")
            return OrderResponse(
                success=False,
                order_id=None,
                message=str(e),
                raw_response={}
            )

    # ===== HELPER: SPREAD BUILDERS =====

    def build_iron_condor_legs(
            self,
            symbol: str,
            expiry_month: str,
            put_strikes: Tuple[float, float],  # (long_put, short_put)
            call_strikes: Tuple[float, float],  # (short_call, long_call)
    ) -> List[Dict]:
        """
        Iron Condor leg-ek építése (helper)

        Args:
            symbol: Underlying
            expiry_month: Lejárat
            put_strikes: (lower_strike, higher_strike) puts
            call_strikes: (lower_strike, higher_strike) calls

        Returns:
            Lista a leg dict-ekről, használható place_option_spread_order-hez
        """
        long_put = self.get_option_contract_info(symbol, put_strikes[0], 'P', expiry_month)[0]
        short_put = self.get_option_contract_info(symbol, put_strikes[1], 'P', expiry_month)[0]
        short_call = self.get_option_contract_info(symbol, call_strikes[0], 'C', expiry_month)[0]
        long_call = self.get_option_contract_info(symbol, call_strikes[1], 'C', expiry_month)[0]

        return [
            {'conid': long_put.conid, 'ratio': 1, 'side': 'BUY'},
            {'conid': short_put.conid, 'ratio': 1, 'side': 'SELL'},
            {'conid': short_call.conid, 'ratio': 1, 'side': 'SELL'},
            {'conid': long_call.conid, 'ratio': 1, 'side': 'BUY'},
        ]

    def build_credit_spread_legs(
            self,
            symbol: str,
            expiry_month: str,
            short_strike: float,
            long_strike: float,
            right: Union[str, OptionRight]
    ) -> List[Dict]:
        """
        Credit spread leg-ek építése

        Args:
            symbol: Underlying
            expiry_month: Lejárat
            short_strike: Short leg strike
            long_strike: Long leg strike (protection)
            right: 'C' vagy 'P'

        Returns:
            Lista a leg dict-ekről
        """
        if isinstance(right, OptionRight):
            right = right.value

        short_contract = self.get_option_contract_info(symbol, short_strike, right, expiry_month)[0]
        long_contract = self.get_option_contract_info(symbol, long_strike, right, expiry_month)[0]

        return [
            {'conid': short_contract.conid, 'ratio': 1, 'side': 'SELL'},
            {'conid': long_contract.conid, 'ratio': 1, 'side': 'BUY'},
        ]

    # ===== BRACKET ORDERS =====

    def place_bracket_order(
            self,
            symbol: str,
            side: Union[str, OrderSide],
            quantity: int,
            entry_price: float,
            stop_loss_price: float,
            take_profit_price: float,
            tag: Optional[str] = None
    ) -> OrderResponse:
        """
        Bracket order (entry + stop + profit)
        """
        if isinstance(side, OrderSide):
            side = side.value

        conid = self.get_stock_conid(symbol)

        if not tag:
            tag = f"{symbol}_bracket_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Parent
        parent = make_order_request(
            conid=conid,
            side=side,
            quantity=quantity,
            order_type='LMT',
            price=entry_price,
            acct_id=self.account_id,
            coid=tag
        )

        # Stop loss
        stop_loss = make_order_request(
            conid=conid,
            side='SELL' if side == 'BUY' else 'BUY',
            quantity=quantity,
            order_type='STP',
            price=stop_loss_price,
            acct_id=self.account_id,
            parent_id=tag
        )

        # Take profit
        take_profit = make_order_request(
            conid=conid,
            side='SELL' if side == 'BUY' else 'BUY',
            quantity=quantity,
            order_type='LMT',
            price=take_profit_price,
            acct_id=self.account_id,
            parent_id=tag
        )

        requests = [parent, stop_loss, take_profit]

        try:
            response = self.client.place_order(
                requests,
                self.default_answers,
                self.account_id
            ).data

            self.logger.info(f"Bracket order placed: {symbol} {side} {quantity}")

            return OrderResponse(
                success=True,
                order_id=tag,
                message="Bracket order",
                raw_response=response
            )

        except Exception as e:
            self.logger.error(f"Bracket order failed: {e}")
            return OrderResponse(
                success=False,
                order_id=None,
                message=str(e),
                raw_response={}
            )

    # ===== ORDER TRACKING =====

    def get_live_orders(self) -> List[OrderInfo]:
        """Aktív orderek"""
        try:
            response = self.client.live_orders().data

            orders = []
            for order_data in response:
                orders.append(self._parse_order_info(order_data))

            self.logger.info(f"Retrieved {len(orders)} live orders")
            return orders

        except Exception as e:
            self.logger.error(f"Failed to get live orders: {e}")
            return []

    def get_order_by_id(self, order_id: str) -> Optional[OrderInfo]:
        """Order lekérése ID alapján"""
        try:
            # Live orders
            live_orders = self.get_live_orders()
            for order in live_orders:
                if order.order_id == order_id:
                    return order

            # History
            history = self.get_order_history(days=30)
            for order in history:
                if order.order_id == order_id:
                    return order

            self.logger.warning(f"Order not found: {order_id}")
            return None

        except Exception as e:
            self.logger.error(f"Failed to get order {order_id}: {e}")
            return None

    def get_order_history(
            self,
            days: int = 7,
            filters: Optional[str] = None
    ) -> List[OrderInfo]:
        """Order history"""
        try:
            response = self.client.orders_history(
                account_id=self.account_id,
                filters=filters
            ).data

            orders = []

            if isinstance(response, dict):
                orders_data = response.get('orders', [])
            else:
                orders_data = response

            for order_data in orders_data:
                orders.append(self._parse_order_info(order_data))

            self.logger.info(f"Retrieved {len(orders)} historical orders")
            return orders

        except Exception as e:
            self.logger.error(f"Failed to get order history: {e}")
            return []

    def get_trades(
            self,
            days: int = 7,
            conid: Optional[int] = None
    ) -> List[Trade]:
        """Executed trades"""
        try:
            response = self.client.trades().data

            trades = []
            for trade_data in response:
                if conid and trade_data.get('conid') != conid:
                    continue

                trades.append(Trade(
                    execution_id=trade_data.get('execution_id', ''),
                    order_id=trade_data.get('order_id', ''),
                    symbol=trade_data.get('symbol', ''),
                    conid=trade_data.get('conid', 0),
                    side=trade_data.get('side', ''),
                    quantity=float(trade_data.get('size', 0)),
                    price=float(trade_data.get('price', 0)),
                    time=trade_data.get('time', ''),
                    commission=float(trade_data.get('commission', 0)) if trade_data.get('commission') else None,
                    account=trade_data.get('account', ''),
                    raw_data=trade_data
                ))

            self.logger.info(f"Retrieved {len(trades)} trades")
            return trades

        except Exception as e:
            self.logger.error(f"Failed to get trades: {e}")
            return []

    def cancel_order(self, order_id: str) -> bool:
        """Order törlése"""
        try:
            response = self.client.cancel_order(
                account_id=self.account_id,
                order_id=order_id
            ).data

            success = response.get('msg', '') == 'Request was submitted'

            if success:
                self.logger.info(f"Order cancelled: {order_id}")
            else:
                self.logger.warning(f"Order cancel failed: {order_id}")

            return success

        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def cancel_all_orders(self) -> int:
        """Összes aktív order törlése"""
        orders = self.get_live_orders()
        cancelled = 0

        for order in orders:
            if self.cancel_order(order.order_id):
                cancelled += 1

        self.logger.info(f"Cancelled {cancelled}/{len(orders)} orders")
        return cancelled

    def wait_for_order_fill(
            self,
            order_id: str,
            timeout: int = 60,
            check_interval: float = 1.0
    ) -> Optional[OrderInfo]:
        """Várj amíg filled lesz"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            order = self.get_order_by_id(order_id)

            if not order:
                self.logger.warning(f"Order disappeared: {order_id}")
                return None

            if order.status in ['Filled', 'Cancelled', 'Rejected']:
                self.logger.info(f"Order {order_id} finished: {order.status}")
                return order

            time.sleep(check_interval)

        self.logger.warning(f"Order {order_id} timeout after {timeout}s")
        return None

    # ===== CONVENIENCE METHODS =====

    def get_filled_orders(self, days: int = 7) -> List[OrderInfo]:
        """Filled orderek"""
        return self.get_order_history(days=days, filters='Filled')

    def get_cancelled_orders(self, days: int = 7) -> List[OrderInfo]:
        """Cancelled orderek"""
        return self.get_order_history(days=days, filters='Cancelled')

    def get_active_orders_by_symbol(self, symbol: str) -> List[OrderInfo]:
        """Aktív orderek egy symbolra"""
        all_orders = self.get_live_orders()
        return [o for o in all_orders if o.symbol == symbol]

    def has_active_order_for_symbol(self, symbol: str) -> bool:
        """Van-e aktív order?"""
        return len(self.get_active_orders_by_symbol(symbol)) > 0

    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """Order státusz"""
        order = self.get_order_by_id(order_id)
        if not order:
            return None

        try:
            return OrderStatus(order.status)
        except ValueError:
            self.logger.warning(f"Unknown status: {order.status}")
            return None

    # ===== WEBSOCKET =====

    def start_websocket(self) -> IbkrWsClient:
        """WebSocket indítása"""
        if self._ws_client is None:
            self._ws_client = IbkrWsClient(
                cacert=self._cacert,
                account_id=self.account_id
            )
            self._ws_client.start()
            self.logger.info("WebSocket started")

        return self._ws_client

    def subscribe_market_data(self, symbol: str, fields: Optional[List[str]] = None):
        """Subscribe to market data"""
        if self._ws_client is None:
            self.start_websocket()

        conid = self.get_stock_conid(symbol)

        if fields is None:
            fields = ['55', '71', '84', '86', '88', '85', '87']

        self._ws_client.subscribe(
            channel=f'md+{conid}',
            data={'fields': fields}
        )

        self.logger.info(f"Subscribed to market data: {symbol}")

    def subscribe_order_updates(self):
        """Subscribe to order updates"""
        if self._ws_client is None:
            self.start_websocket()

        self._ws_client.subscribe(channel='or')
        self.logger.info("Subscribed to order updates")

    def subscribe_trades(self):
        """Subscribe to trade updates"""
        if self._ws_client is None:
            self.start_websocket()

        self._ws_client.subscribe(channel='tr')
        self.logger.info("Subscribed to trades")

    def subscribe_pnl(self):
        """Subscribe to PnL updates"""
        if self._ws_client is None:
            self.start_websocket()

        self._ws_client.subscribe(channel='pl')
        self.logger.info("Subscribed to PnL")

    def subscribe_account_summary(self):
        """Subscribe to account summary"""
        if self._ws_client is None:
            self.start_websocket()

        self._ws_client.subscribe(channel=f'sd+{self.account_id}')
        self.logger.info("Subscribed to account summary")

    def subscribe_account_ledger(self):
        """Subscribe to account ledger"""
        if self._ws_client is None:
            self.start_websocket()

        self._ws_client.subscribe(channel=f'ld+{self.account_id}')
        self.logger.info("Subscribed to account ledger")

    def get_realtime_data(self, key: IbkrWsKey, timeout: int = 5) -> Optional[Dict]:
        """Real-time data lekérése (blocking)"""
        if self._ws_client is None:
            raise RuntimeError("WebSocket not started")

        qa = self._ws_client.new_queue_accessor(key)

        start_time = time.time()
        while time.time() - start_time < timeout:
            if not qa.empty():
                return qa.get()
            time.sleep(0.1)

        return None

    def close_websocket(self):
        """WebSocket bezárása"""
        if self._ws_client:
            self._ws_client.shutdown()
            self._ws_client = None
            self.logger.info("WebSocket closed")

    # ===== HELPER METHODS =====

    def _parse_order_info(self, order_data: Dict) -> OrderInfo:
        """Parse order data"""
        return OrderInfo(
            order_id=str(order_data.get('orderId', order_data.get('order_id', ''))),
            account=order_data.get('acct', order_data.get('account', self.account_id)),
            symbol=order_data.get('ticker', order_data.get('symbol', '')),
            conid=int(order_data.get('conid', order_data.get('conidEx', 0))),
            side=order_data.get('side', order_data.get('action', '')),
            order_type=order_data.get('orderType', order_data.get('order_type', '')),
            quantity=float(order_data.get('totalSize', order_data.get('quantity', 0))),
            filled_quantity=float(order_data.get('filledQuantity', order_data.get('filled', 0))),
            remaining_quantity=float(order_data.get('remainingQuantity', order_data.get('remaining', 0))),
            price=float(order_data.get('price', 0)) if order_data.get('price') else None,
            avg_fill_price=float(order_data.get('avgPrice', 0)) if order_data.get('avgPrice') else None,
            status=order_data.get('status', order_data.get('orderStatus', 'Unknown')),
            time_submitted=order_data.get('lastExecutionTime', order_data.get('time_submitted')),
            time_updated=order_data.get('lastExecutionTime_r', order_data.get('time_updated')),
            commission=float(order_data.get('commission', 0)) if order_data.get('commission') else None,
            text=order_data.get('text', order_data.get('order_status_text', '')),
            raw_data=order_data
        )

    def _extract_success(self, response: Union[Dict, List]) -> bool:
        """Extract success from response"""
        if isinstance(response, list):
            return response[0].get('success', False) if response else False
        return response.get('success', False)

    def _extract_order_id(self, response: Union[Dict, List]) -> Optional[str]:
        """Extract order ID from response"""
        if isinstance(response, list):
            return response[0].get('order_id') if response else None
        return response.get('order_id')


# ===== HELPER FUNCTIONS =====

def setup_ibind_env(account_id: str, cacert_path: str):
    """Environment variables beállítása"""
    os.environ['IBIND_ACCOUNT_ID'] = account_id
    os.environ['IBIND_CACERT'] = cacert_path


# ===== USAGE EXAMPLES =====

# if __name__ == '__main__':
#     # Setup
#     # setup_ibind_env('DU123456', '/path/to/cacert.pem')
#
#     client = IBTradingClient(
#         account_id='DU123456',
#         log_level='INFO'
#     )
#
#     # Connection check
#     if not client.check_connection():
#         print("Gateway not available!")
#         exit(1)
#
#     print("\n=== ACCOUNT INFO ===")
#     balance = client.get_account_balance()
#     print(f"Balance: {balance}")
#
#     positions = client.get_positions()
#     for pos in positions:
#         print(f"{pos.ticker}: {pos.quantity} @ ${pos.avg_price}")
#
#     print("\n=== STOCK ORDER (DEMO) ===")
#     # response = client.place_stock_order(
#     #     symbol='AAPL',
#     #     side=OrderSide.BUY,
#     #     quantity=1,
#     #     order_type=OrderType.LIMIT,
#     #     limit_price=210.00
#     # )
#     # print(f"Response: {response}")
#
#     print("\n=== 0DTE OPTION ORDER (DEMO) ===")
#     # response = client.place_option_order(
#     #     symbol='SPX',
#     #     strike=5800,
#     #     right=OptionRight.CALL,
#     #     expiry_month='DEC24',
#     #     side=OrderSide.BUY,
#     #     quantity=1
#     # )
#     # print(f"Response: {response}")
#
#     print("\n=== IRON CONDOR SPREAD (DEMO) ===")
#     # # Build legs
#     # legs = client.build_iron_condor_legs(
#     #     symbol='SPX',
#     #     expiry_month='DEC24',
#     #     put_strikes=(5700, 5750),
#     #     call_strikes=(5850, 5900)
#     # )
#     #
#     # # Place spread
#     # response = client.place_option_spread_order(
#     #     legs=legs,
#     #     side=OrderSide.BUY,
#     #     quantity=1,
#     #     order_type=OrderType.LIMIT,
#     #     limit_price=1.50  # Net credit
#     # )
#     # print(f"Response: {response}")
#
#     print("\n=== ORDER TRACKING ===")
#     live_orders = client.get_live_orders()
#     print(f"Live orders: {len(live_orders)}")
#
#     history = client.get_order_history(days=7)
#     print(f"History: {len(history)} orders")
#
#     trades = client.get_trades(days=7)
#     print(f"Trades: {len(trades)} executions")