import requests
import random
import time
import threading
import json
import urllib.parse
from email.utils import parsedate_to_datetime
import datetime
from requests.exceptions import RequestException

JUPITER_BASE_URL = "https://api.jup.ag/swap/v1"
SOL_MINT = "So11111111111111111111111111111111111111112"
DEFAULT_SLIPPAGE_BPS = 100
DEFAULT_TIMEOUT = 15

class JupiterError(Exception):
    pass

class JupiterRateLimitedError(JupiterError):
    pass

class RequestState:
    def __init__(self, cond):
        self.cond = cond
        self.completed = False
        self.result = None

class JupiterClient:
    def __init__(
        self,
        slippage_bps=DEFAULT_SLIPPAGE_BPS,
        timeout=DEFAULT_TIMEOUT,
        max_retries=2,
        retry_base_delay=2.0,
        retry_max_delay=12.0,
    ):
        self.slippage_bps = int(slippage_bps)
        self.timeout = int(timeout)
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay = max(0.1, float(retry_base_delay))
        self.retry_max_delay = max(self.retry_base_delay, float(retry_max_delay))
        
        # Rate Limiting & Coalescing State
        self._in_flight_requests = {}
        self._limiter_lock = threading.Lock()
        self._exit_priority_cv = threading.Condition(self._limiter_lock)
        self._entry_cv = threading.Condition(self._limiter_lock)
        self._exit_waiters = 0

    def _parse_retry_after(self, retry_after_header):
        if not retry_after_header:
            return None
        try:
            return float(retry_after_header)
        except ValueError:
            pass
        try:
            dt = parsedate_to_datetime(retry_after_header)
            now = datetime.datetime.now(datetime.timezone.utc)
            delay = (dt - now).total_seconds()
            return max(0.0, delay)
        except Exception:
            return None

    def _canonicalize_request(self, method, url, params=None, json_data=None):
        canon_params = ()
        if params:
            canon_params = tuple(sorted((str(k), str(v)) for k, v in params.items()))
        canon_json = ""
        if json_data:
            canon_json = json.dumps(json_data, sort_keys=True)
        return f"{method}:{url}:{canon_params}:{canon_json}"

    def _request_with_retry(self, method, url, params=None, json_data=None, is_exit=False):
        canonical_key = self._canonicalize_request(method, url, params, json_data)
        
        with self._limiter_lock:
            if canonical_key in self._in_flight_requests:
                state = self._in_flight_requests[canonical_key]
                while not state.completed:
                    state.cond.wait()
                if isinstance(state.result, Exception):
                    raise state.result
                return state.result
            
            state = RequestState(threading.Condition(self._limiter_lock))
            self._in_flight_requests[canonical_key] = state
            
            if is_exit:
                self._exit_waiters += 1

        attempt = 0
        last_http_status = None
        total_rate_limit_wait = 0.0
        last_retry_after_ms = 0.0
        
        try:
            while attempt <= self.max_retries:
                with self._limiter_lock:
                    if not is_exit:
                        while self._exit_waiters > 0:
                            self._entry_cv.wait()
                
                try:
                    if method.upper() == "GET":
                        response = requests.get(url, params=params, timeout=self.timeout)
                    else:
                        response = requests.post(url, json=json_data, timeout=self.timeout)
                        
                    last_http_status = response.status_code
                    
                except RequestException as exc:
                    if attempt >= self.max_retries:
                        raise JupiterError(f"Jupiter request failed after {attempt+1} attempts: {exc}") from exc
                    delay = min(self.retry_max_delay, self.retry_base_delay * (2 ** attempt))
                    delay += random.uniform(0.0, min(0.5, delay * 0.25))
                    time.sleep(delay)
                    attempt += 1
                    continue
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        result = {
                            "data": data,
                            "telemetry": {
                                "jupiter_http_status": 200,
                                "jupiter_retry_count": attempt,
                                "jupiter_retry_after_ms": last_retry_after_ms,
                                "jupiter_rate_limit_wait_ms": total_rate_limit_wait,
                                "quote_attempt": attempt + 1,
                                "quote_timestamp": time.time(),
                                "jupiter_failure_reason": None
                            }
                        }
                        return result
                    except ValueError as exc:
                        raise JupiterError(f"Invalid Jupiter JSON response: {response.text[:500]}") from exc

                if response.status_code == 400:
                    raise JupiterError(f"Deterministic client error (400): {response.text[:500]}")
                    
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt >= self.max_retries:
                        raise JupiterRateLimitedError(f"Jupiter HTTP {response.status_code} after {attempt+1} attempts")
                        
                    retry_after_val = self._parse_retry_after(response.headers.get("Retry-After"))
                    if retry_after_val is not None:
                        delay = min(self.retry_max_delay, retry_after_val)
                        last_retry_after_ms = retry_after_val * 1000.0
                    else:
                        delay = self.retry_base_delay * (2 ** attempt)
                        delay = min(self.retry_max_delay, delay)
                        delay += random.uniform(0.0, min(0.5, delay * 0.25))
                        
                    total_rate_limit_wait += (delay * 1000.0)
                    time.sleep(delay)
                    attempt += 1
                    continue
                    
                raise JupiterError(f"Jupiter HTTP {response.status_code}: {response.text[:500]}")
                
            raise JupiterRateLimitedError("Max retries exceeded")
            
        except Exception as final_exc:
            result = final_exc
            raise
        finally:
            with self._limiter_lock:
                if is_exit:
                    self._exit_waiters -= 1
                    if self._exit_waiters == 0:
                        self._entry_cv.notify_all()
                state = self._in_flight_requests.pop(canonical_key, None)
                if state:
                    state.completed = True
                    state.result = result if 'result' in locals() else JupiterError("Unknown error")
                    state.cond.notify_all()

    def get_quote(self, input_mint, output_mint, amount, slippage_bps=None, is_exit=False):
        amount = int(amount)
        if amount <= 0:
            raise JupiterError("Amount must be greater than zero")

        params = {
            "inputMint": str(input_mint),
            "outputMint": str(output_mint),
            "amount": str(amount),
            "slippageBps": str(self.slippage_bps if slippage_bps is None else int(slippage_bps)),
        }
        url = f"{JUPITER_BASE_URL}/quote"
        
        response = self._request_with_retry("GET", url, params=params, is_exit=is_exit)
        data = response["data"]
        
        if not data.get("outAmount"):
            raise JupiterError(f"Jupiter returned no output amount: {data}")
            
        data["_telemetry"] = response["telemetry"]
        return data

    def validate_quote(self, quote, max_price_impact_pct=2.0):
        if not isinstance(quote, dict):
            return False, "Quote is not a dictionary"
        if not quote.get("inputMint"):
            return False, "Missing inputMint"
        if not quote.get("outputMint"):
            return False, "Missing outputMint"
        if int(quote.get("inAmount", 0)) <= 0:
            return False, "Invalid input amount"
        if int(quote.get("outAmount", 0)) <= 0:
            return False, "Invalid output amount"
        if not quote.get("routePlan"):
            return False, "No route returned"
        try:
            price_impact = float(quote.get("priceImpactPct", 0.0))
        except (TypeError, ValueError):
            return False, "Invalid price impact"
        if price_impact > float(max_price_impact_pct):
            return False, f"Price impact {price_impact:.4f}% exceeds maximum {float(max_price_impact_pct):.4f}%"
        return True, "Quote accepted"

    def build_swap_transaction(self, quote, user_public_key, wrap_and_unwrap_sol=True, is_exit=False):
        if not quote:
            raise JupiterError("Quote is empty")
        if not user_public_key:
            raise JupiterError("user_public_key is required")

        clean_quote = {k: v for k, v in quote.items() if k != "_telemetry"}

        payload = {
            "quoteResponse": clean_quote,
            "userPublicKey": str(user_public_key),
            "wrapAndUnwrapSol": bool(wrap_and_unwrap_sol),
            "dynamicComputeUnitLimit": True,
            "prioritizationFeeLamports": "auto",
        }
        url = f"{JUPITER_BASE_URL}/swap"
        
        response = self._request_with_retry("POST", url, json_data=payload, is_exit=is_exit)
        data = response["data"]
        
        if not data.get("swapTransaction"):
            raise JupiterError("Jupiter returned no swapTransaction")
            
        return data
