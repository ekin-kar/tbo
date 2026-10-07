"""
Minimal Binance USD-M futures REST client (signed requests with `requests`, nothing else).

Conditional orders (STOP_MARKET etc.) go through the Algo Order API (/fapi/v1/algoOrder): since
Dec 2025 /fapi/v1/order rejects them with -4120 STOP_ORDER_SWITCH_ALGO.
"""
import hashlib
import hmac
import time
from urllib.parse import urlencode

import requests

LIVE = "https://fapi.binance.com"
TESTNET = "https://demo-fapi.binance.com"


class BinanceError(Exception):
    def __init__(self, status, code, msg):
        super().__init__(f"HTTP {status} code {code}: {msg}")
        self.status, self.code, self.msg = status, code, msg


class Futures:
    def __init__(self, key, secret, testnet=False, base_url=None, recv_window=5000):
        self.key, self.secret = key, secret.encode() if secret else b""
        self.base = base_url or (TESTNET if testnet else LIVE)
        self.recv_window = recv_window
        self.s = requests.Session()
        self.s.headers["X-MBX-APIKEY"] = key or ""
        self.offset = 0
        self.sync_time()

    # ── plumbing ──
    def sync_time(self):
        st = self._req("GET", "/fapi/v1/time")["serverTime"]
        self.offset = st - int(time.time() * 1000)

    def now_ms(self):
        return int(time.time() * 1000) + self.offset

    def _req(self, method, path, params=None, signed=False):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        if signed:
            params["timestamp"] = self.now_ms()
            params["recvWindow"] = self.recv_window
            q = urlencode(params)
            params_str = q + "&signature=" + hmac.new(self.secret, q.encode(), hashlib.sha256).hexdigest()
        else:
            params_str = urlencode(params)
        url = f"{self.base}{path}" + (f"?{params_str}" if params_str else "")
        for attempt in range(4):
            try:
                r = self.s.request(method, url, timeout=15)
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
                continue
            if r.status_code in (429, 418) or r.status_code >= 500:
                if attempt == 3 or r.status_code == 418:
                    break
                time.sleep(2 ** (attempt + 1))
                continue
            break
        try:
            data = r.json()
        except ValueError:
            raise BinanceError(r.status_code, None, r.text[:300])
        if r.status_code != 200:
            if isinstance(data, dict) and data.get("code") == -1021:     # timestamp outside recvWindow
                self.sync_time()
            raise BinanceError(r.status_code, data.get("code") if isinstance(data, dict) else None,
                               data.get("msg") if isinstance(data, dict) else str(data))
        return data

    # ── market data ──
    def exchange_info(self, symbol):
        info = self._req("GET", "/fapi/v1/exchangeInfo")
        for s in info["symbols"]:
            if s["symbol"] == symbol:
                f = {x["filterType"]: x for x in s["filters"]}
                return dict(tick=float(f["PRICE_FILTER"]["tickSize"]), step=float(f["LOT_SIZE"]["stepSize"]),
                            min_qty=float(f["LOT_SIZE"]["minQty"]),
                            mkt_step=float(f.get("MARKET_LOT_SIZE", f["LOT_SIZE"])["stepSize"]),
                            mkt_max=float(f.get("MARKET_LOT_SIZE", f["LOT_SIZE"])["maxQty"]),
                            min_notional=float(f.get("MIN_NOTIONAL", {}).get("notional", 5)),
                            status=s["status"])
        raise ValueError(f"symbol {symbol} not found")

    def klines(self, symbol, interval, limit, start_ms=None):
        """[(open_ms, o, h, l, c, close_ms), ...] oldest first, including the candle still forming."""
        raw = self._req("GET", "/fapi/v1/klines", dict(symbol=symbol, interval=interval, limit=limit, startTime=start_ms))
        return [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), int(k[6])) for k in raw]

    def last_price(self, symbol):
        return float(self._req("GET", "/fapi/v1/ticker/price", dict(symbol=symbol))["price"])

    def open_interest_hist(self, symbol, period="1h", limit=100):
        """[(timestamp_ms, open interest USD value), ...] oldest first (public endpoint, last 30 days)."""
        raw = self._req("GET", "/futures/data/openInterestHist", dict(symbol=symbol, period=period, limit=min(int(limit), 500)))
        return sorted((int(r["timestamp"]), float(r["sumOpenInterestValue"])) for r in raw)

    # ── account ──
    def account(self):
        return self._req("GET", "/fapi/v3/account", signed=True)

    def position(self, symbol):
        """Signed position amount (one-way mode) and entry price."""
        rows = self._req("GET", "/fapi/v3/positionRisk", dict(symbol=symbol), signed=True)
        amt = sum(float(r["positionAmt"]) for r in rows)
        entry = next((float(r["entryPrice"]) for r in rows if float(r["positionAmt"]) != 0), 0.0)
        return amt, entry

    def api_restrictions(self):
        """Spot API (api.binance.com): enableWithdrawals, enableFutures, ipRestrict ... (live keys only)."""
        if self.base != LIVE:
            raise BinanceError(0, None, "not available on testnet")
        q = f"timestamp={self.now_ms()}&recvWindow={self.recv_window}"
        sig = hmac.new(self.secret, q.encode(), hashlib.sha256).hexdigest()
        r = self.s.get(f"https://api.binance.com/sapi/v1/account/apiRestrictions?{q}&signature={sig}", timeout=15)
        if r.status_code != 200:
            raise BinanceError(r.status_code, None, r.text[:200])
        return r.json()

    def multi_assets(self):
        return bool(self._req("GET", "/fapi/v1/multiAssetsMargin", signed=True).get("multiAssetsMargin"))

    def symbol_config(self, symbol):
        r = self._req("GET", "/fapi/v1/symbolConfig", dict(symbol=symbol), signed=True)
        return r[0] if isinstance(r, list) and r else r

    def hedge_mode(self):
        return bool(self._req("GET", "/fapi/v1/positionSide/dual", signed=True)["dualSidePosition"])

    def set_leverage(self, symbol, leverage):
        return self._req("POST", "/fapi/v1/leverage", dict(symbol=symbol, leverage=int(leverage)), signed=True)

    def user_trades(self, symbol, limit=50):
        return self._req("GET", "/fapi/v1/userTrades", dict(symbol=symbol, limit=limit), signed=True)

    # ── orders ──
    def market(self, symbol, side, qty, reduce_only=False, client_id=None):
        return self._req("POST", "/fapi/v1/order", dict(symbol=symbol, side=side, type="MARKET", quantity=qty,
                                                         reduceOnly="true" if reduce_only else None,
                                                         newClientOrderId=client_id, newOrderRespType="RESULT"),
                         signed=True)

    def stop_market(self, symbol, side, trigger, qty=None, close_position=False, client_id=None):
        """Conditional STOP_MARKET via the Algo Order API, triggered on the LAST price (as in the backtest)."""
        return self._req("POST", "/fapi/v1/algoOrder", dict(
            algoType="CONDITIONAL", symbol=symbol, side=side, type="STOP_MARKET", triggerPrice=trigger,
            quantity=None if close_position else qty, closePosition="true" if close_position else None,
            workingType="CONTRACT_PRICE", clientAlgoId=client_id), signed=True)

    def open_algo_orders(self, symbol):
        r = self._req("GET", "/fapi/v1/openAlgoOrders", dict(symbol=symbol), signed=True)
        return r if isinstance(r, list) else r.get("orders", [])

    def algo_order(self, algo_id=None, client_id=None):
        return self._req("GET", "/fapi/v1/algoOrder", dict(algoId=algo_id, clientAlgoId=client_id), signed=True)

    def cancel_algo(self, algo_id=None, client_id=None):
        return self._req("DELETE", "/fapi/v1/algoOrder", dict(algoId=algo_id, clientAlgoId=client_id), signed=True)
