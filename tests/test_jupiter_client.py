import pytest
from unittest.mock import MagicMock, patch
import time
import threading
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

def test_full_request_coalescing():
    client = JupiterClient(max_retries=1)
    
    event = threading.Event()
    call_count = [0]
    
    def mock_get(*args, **kwargs):
        call_count[0] += 1
        event.wait()
        return MockResponse(200, {"outAmount": "1000"})
        
    with patch("execution.jupiter_client.requests.get", side_effect=mock_get):
        results = []
        def worker(mint):
            try:
                res = client.get_quote("A", mint, 100)
                results.append(res)
            except Exception as e:
                results.append(e)

        t1 = threading.Thread(target=worker, args=("B",))
        t2 = threading.Thread(target=worker, args=("B",))
        t3 = threading.Thread(target=worker, args=("B",))
        t4 = threading.Thread(target=worker, args=("C",))

        t1.start()
        t2.start()
        t3.start()
        t4.start()
        
        time.sleep(0.5)
        event.set()
        
        t1.join()
        t2.join()
        t3.join()
        t4.join()

        assert call_count[0] == 2
        assert len(results) == 4
        for r in results:
            assert isinstance(r, dict)
            assert r["outAmount"] == "1000"

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
