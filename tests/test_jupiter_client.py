import pytest
from unittest.mock import MagicMock, patch
import time
import threading
import requests
from execution.jupiter_client import JupiterClient, JupiterError, JupiterRateLimitedError

class MockResponse:
    def __init__(self, status_code, json_data=None, headers=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        if not self._json:
            raise ValueError("No JSON")
        return self._json

def test_comprehensive_coalescing():
    client = JupiterClient(max_retries=1)
    
    event = threading.Event()
    call_count = [0]
    call_args = []
    
    def mock_get(*args, **kwargs):
        call_count[0] += 1
        call_args.append(kwargs.get('params', {}).get('outputMint'))
        event.wait()
        # Different mock responses based on outputMint to trace which request returned
        mint = kwargs.get('params', {}).get('outputMint')
        if mint == "ERROR_MINT":
            raise requests.exceptions.RequestException("Network Failure")
        return MockResponse(200, {"outAmount": f"1000_{mint}"})
        
    with patch("execution.jupiter_client.requests.get", side_effect=mock_get):
        results = []
        def worker(mint):
            try:
                res = client.get_quote("A", mint, 100)
                results.append((mint, res.get("outAmount") if isinstance(res, dict) else res))
            except Exception as e:
                results.append((mint, type(e).__name__))

        # 1. 3 concurrent identical requests => 1 HTTP call
        t1 = threading.Thread(target=worker, args=("B",))
        t2 = threading.Thread(target=worker, args=("B",))
        t3 = threading.Thread(target=worker, args=("B",))
        
        # 2. different request => independent call
        t4 = threading.Thread(target=worker, args=("C",))
        
        # 4. owner exception shared by all waiters
        t5 = threading.Thread(target=worker, args=("ERROR_MINT",))
        t6 = threading.Thread(target=worker, args=("ERROR_MINT",))

        t1.start()
        t2.start()
        t3.start()
        t4.start()
        t5.start()
        t6.start()
        
        # Wait for threads to hit the barrier
        time.sleep(0.5)
        
        # At this point, we should have exactly 3 HTTP calls (B, C, ERROR_MINT)
        assert call_count[0] == 3
        
        event.set()
        
        t1.join()
        t2.join()
        t3.join()
        t4.join()
        t5.join()
        t6.join()

        # 3. owner success shared by all waiters (all B got 1000_B)
        b_results = [r for m, r in results if m == "B"]
        assert len(b_results) == 3
        assert all(r == "1000_B" for r in b_results)
        
        c_results = [r for m, r in results if m == "C"]
        assert len(c_results) == 1
        assert c_results[0] == "1000_C"
        
        err_results = [r for m, r in results if m == "ERROR_MINT"]
        assert len(err_results) == 2
        print("ERR RESULTS:", err_results)
        # Should raise JupiterError mapping from RequestException
        assert all(r == "JupiterError" for r in err_results)
        
        # 5. cleanup after completion
        # _in_flight_requests should be completely empty
        assert len(client._in_flight_requests) == 0
        
        # 6. subsequent request after completion creates a new HTTP request
        event.clear()
        
        def late_worker():
            try:
                res = client.get_quote("A", "B", 100)
                results.append(("LATE_B", res.get("outAmount")))
            except Exception as e:
                results.append(("LATE_B", e))
                
        t7 = threading.Thread(target=late_worker)
        t7.start()
        time.sleep(0.1)
        event.set()
        t7.join()
        
        assert call_count[0] == 5 # 3 original + 1 retry for ERROR_MINT + 1 for LATE_B
        late_results = [r for m, r in results if m == "LATE_B"]
        assert len(late_results) == 1
        assert late_results[0] == "1000_B"
        
        # 7. no deadlock is inherently proven by all threads joining and exiting.

def test_retry_after_seconds():
    client = JupiterClient(max_retries=2, retry_base_delay=0.1, retry_max_delay=5.0)
    
    responses = [
        MockResponse(429, headers={"Retry-After": "1.5"}),
        MockResponse(200, {"outAmount": "2000"})
    ]
    
    def mock_get(*args, **kwargs):
        if responses:
            return responses.pop(0)
        return MockResponse(200, {"outAmount": "1000"})

    start_time = time.time()
    with patch("execution.jupiter_client.requests.get", side_effect=mock_get):
        res = client.get_quote("A", "B", 100)
        
    elapsed = time.time() - start_time
    assert elapsed >= 1.5
    assert res["_telemetry"]["jupiter_retry_after_ms"] == 1500.0
    assert res["_telemetry"]["jupiter_retry_count"] == 1

def test_deterministic_400_fails_fast():
    client = JupiterClient(max_retries=3)
    
    with patch("execution.jupiter_client.requests.get", return_value=MockResponse(400, text="Invalid mint")):
        with pytest.raises(JupiterError) as exc:
            client.get_quote("A", "B", 100)
        assert "Deterministic client error (400)" in str(exc.value)

def test_bounded_failure_429():
    client = JupiterClient(max_retries=1, retry_base_delay=0.1)
    
    with patch("execution.jupiter_client.requests.get", return_value=MockResponse(429, text="Rate Limited")):
        with pytest.raises(JupiterRateLimitedError) as exc:
            client.get_quote("A", "B", 100)
        assert "Jupiter HTTP 429 after 2 attempts" in str(exc.value)

def test_exit_priority():
    client = JupiterClient()
    
    gate_event = threading.Event()
    order_of_execution = []
    
    def mock_get(url, **kwargs):
        if "quote" in url:
            gate_event.wait()
            order_of_execution.append("ENTRY")
            return MockResponse(200, {"outAmount": "100"})
        else:
            order_of_execution.append("EXIT")
            return MockResponse(200, {"swapTransaction": "xyz"})

    with patch("execution.jupiter_client.requests.get", side_effect=mock_get), \
         patch("execution.jupiter_client.requests.post", side_effect=mock_get):
         
        def entry_worker():
            client.get_quote("A", "B", 100)
            
        def exit_worker():
            client.build_swap_transaction({"inAmount":"100"}, "C", is_exit=True)

        t_entry1 = threading.Thread(target=entry_worker)
        t_entry1.start()
        
        time.sleep(0.1) 
        
        t_exit = threading.Thread(target=exit_worker)
        t_exit.start()
        
        time.sleep(0.1)
        
        t_entry2 = threading.Thread(target=entry_worker)
        t_entry2.start()
        
        time.sleep(0.1)
        
        gate_event.set()
        
        t_entry1.join()
        t_exit.join()
        t_entry2.join()
        
        assert order_of_execution.count("EXIT") == 1
        # Because of request coalescing, the two ENTRY threads for ("A", "B", 100)
        # merge into a single mock_get call! So count("ENTRY") == 1.
        assert order_of_execution.count("ENTRY") == 1
        # Exit didn't block on gate_event, so it finishes before ENTRY unblocks.
        assert order_of_execution == ["EXIT", "ENTRY"]

def test_swap_http_retry_does_not_resubmit():
    client = JupiterClient(max_retries=1, retry_base_delay=0.1)
    
    responses = [
        MockResponse(429),
        MockResponse(200, {"swapTransaction": "base64bytes"})
    ]
    
    def mock_post(*args, **kwargs):
        return responses.pop(0)

    with patch("execution.jupiter_client.requests.post", side_effect=mock_post):
        res = client.build_swap_transaction({"inAmount": "1"}, "pubkey")
        assert res["swapTransaction"] == "base64bytes"
