import pytest
import time
import uuid
from execution.live_trader import LiveTrader
from database.execution_order_logger import ExecutionOrderLogger
from trading.portfolio import Portfolio
from unittest.mock import MagicMock, patch

class DummyCoin:
    def __init__(self, signal_id=None):
        self.symbol = "TEST"
        self.contract = "TEST_CONTRACT_123"
        self.signal_id = signal_id or f"SIG_{uuid.uuid4().hex[:8]}"
        self.strategy_id = "S6_Moonshot_Ladder"
        self.liquidity = 50000.0

@pytest.fixture
def mock_portfolio():
    port = Portfolio()
    port.wallet_public_key = "test_wallet"
    port.cash = 100.0
    port.can_open_trade = MagicMock(return_value=True)
    port.refresh = MagicMock()
    return port

@pytest.fixture
def live_trader(mock_portfolio):
    trader = LiveTrader(mock_portfolio)
    return trader

class TestLiveShadow:
    def test_shadow_calibration_cap(self, live_trader):
        coin = DummyCoin()
        
        with patch('execution.live_executor.LiveExecutor.prepare_buy') as mock_prep:
            mock_prep.return_value = MagicMock(success=True, error=None, telemetry={"quoted_price": 1.0})
            
            # Request $50, should cap at $1.00
            pos = live_trader.buy(coin, 50.0)
            
            assert pos is not None
            assert pos.invested_amount == 1.0
            
    def test_idempotency_prevents_duplicates(self, live_trader):
        coin = DummyCoin(f"SIG_IDEMP_TEST_{uuid.uuid4().hex[:8]}")
        
        with patch('execution.live_executor.LiveExecutor.prepare_buy') as mock_prep:
            mock_prep.return_value = MagicMock(success=True, error=None, telemetry={"quoted_price": 1.0})
            
            # First buy
            pos1 = live_trader.buy(coin, 1.0)
            assert pos1 is not None
            
            # Second buy with same signal
            pos2 = live_trader.buy(coin, 1.0)
            assert pos2 is None # Idempotency should block this

    def test_structural_safety_bypasses_signing(self, live_trader):
        coin = DummyCoin(f"SIG_SAFE_TEST_{uuid.uuid4().hex[:8]}")
        
        with patch('execution.live_executor.LiveExecutor.prepare_buy') as mock_prep:
            mock_prep.return_value = MagicMock(success=True, error=None, telemetry={"quoted_price": 1.0})
            
            # Ensure signer is never called
            with patch('execution.live_signer.LiveSigner.sign') as mock_sign:
                with patch('execution.solana_sender.SolanaSender.send') as mock_send:
                    pos = live_trader.buy(coin, 1.0)
                    assert pos is not None
                    
                    mock_sign.assert_not_called()
                    mock_send.assert_not_called()
