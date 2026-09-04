import pytest
from unittest.mock import Mock, MagicMock
from execution.fee_resolver import FeeResolver
from solders.transaction import VersionedTransaction
from solders.message import MessageV0, MessageHeader
from solders.pubkey import Pubkey
from solders.instruction import CompiledInstruction
from solders.hash import Hash

class MockRpcClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.called_with = []

    def _rpc(self, method, params):
        self.called_with.append((method, params))
        if self.error:
            raise self.error
        return self.response

def create_mock_transaction(cu_limit=200000, num_signatures=1, has_cu_limit=True, malformed_cu=False, num_readonly_signed=0, num_readonly_unsigned=0):
    header = MessageHeader(
        num_required_signatures=num_signatures,
        num_readonly_signed_accounts=num_readonly_signed,
        num_readonly_unsigned_accounts=num_readonly_unsigned
    )
    
    # 3 accounts: 1 writable signed, 1 writable unsigned, 1 readonly unsigned
    pk1 = Pubkey.default()
    pk2 = Pubkey.default()
    pk3 = Pubkey.from_string("ComputeBudget111111111111111111111111111111")
    account_keys = [pk1, pk2, pk3]
    
    instructions = []
    if has_cu_limit:
        if malformed_cu:
            # missing length
            data = bytes([2, 1, 0])
        else:
            limit_bytes = cu_limit.to_bytes(4, "little")
            data = bytes([2]) + limit_bytes
            
        instructions.append(CompiledInstruction(2, data, b''))
        
    recent_blockhash = Hash.default()
    message = MessageV0(header, account_keys, recent_blockhash, instructions, [])
    # VersionedTransaction normally takes signatures, we can mock it
    
    tx = MagicMock(spec=VersionedTransaction)
    tx.message = message
    return tx

class TestFeeResolver:

    def test_writable_account_extraction(self):
        rpc = MockRpcClient([])
        resolver = FeeResolver(rpc)
        
        # 1 req sig, 0 readonly signed, 1 readonly unsigned => 2 writable out of 3 total
        tx = create_mock_transaction(num_signatures=1, num_readonly_signed=0, num_readonly_unsigned=1)
        writable = resolver.extract_writable_accounts(tx)
        assert len(writable) == 2
        assert "11111111111111111111111111111111" in writable

    def test_missing_compute_unit_limit(self):
        rpc = MockRpcClient([])
        resolver = FeeResolver(rpc)
        tx = create_mock_transaction(has_cu_limit=False)
        limit = resolver.extract_compute_unit_limit(tx)
        assert limit is None

    def test_malformed_compute_unit_limit(self):
        rpc = MockRpcClient([])
        resolver = FeeResolver(rpc)
        tx = create_mock_transaction(malformed_cu=True)
        limit = resolver.extract_compute_unit_limit(tx)
        assert limit is None
        
        # Test estimate fees rejects it
        res = resolver.estimate_network_fees(tx)
        assert res["fee_estimation_status"] == "UNAVAILABLE"

    def test_valid_rpc_response_and_p75(self):
        # 10 samples from 10 to 100
        samples = [{"prioritizationFee": i * 10} for i in range(1, 11)]
        rpc = MockRpcClient(samples)
        resolver = FeeResolver(rpc)
        
        tx = create_mock_transaction(cu_limit=200_000)
        res = resolver.estimate_network_fees(tx)
        
        assert res["fee_estimation_status"] == "COMPLETE"
        
        # 10 samples: 10, 20, 30, 40, 50, 60, 70, 80, 90, 100
        # P75 of prioritizationFee array = 77.5
        # priority_fee_lamports = 77.5
        assert res["priority_fee_lamports"] == 77.5
        
        # compute_unit_price = 77.5 * 1_000_000 / 200_000 = 387.5
        assert res["compute_unit_price_micro_lamports"] == 387.5
        
        # Base fee = 5000 (1 signature)
        assert res["base_fee_lamports"] == 5000.0
        assert res["total_network_fee_lamports"] == 5077.5

    def test_all_zero_prioritization_fees(self):
        samples = [{"prioritizationFee": 0} for _ in range(5)]
        rpc = MockRpcClient(samples)
        resolver = FeeResolver(rpc)
        
        tx = create_mock_transaction(cu_limit=200_000)
        res = resolver.estimate_network_fees(tx)
        
        assert res["fee_estimation_status"] == "COMPLETE"
        assert res["compute_unit_price_micro_lamports"] == 0.0
        assert res["priority_fee_lamports"] == 0.0
        assert res["total_network_fee_lamports"] == 5000.0

    def test_empty_rpc_response(self):
        rpc = MockRpcClient([])
        resolver = FeeResolver(rpc)
        tx = create_mock_transaction()
        res = resolver.estimate_network_fees(tx)
        assert res["fee_estimation_status"] == "COMPLETE"
        assert res["compute_unit_price_micro_lamports"] == 0.0

    def test_malformed_rpc_response(self):
        rpc = MockRpcClient("not a list")
        resolver = FeeResolver(rpc)
        tx = create_mock_transaction()
        res = resolver.estimate_network_fees(tx)
        assert res["fee_estimation_status"] == "UNAVAILABLE"

    def test_rpc_error(self):
        rpc = MockRpcClient(error=Exception("RPC timeout"))
        resolver = FeeResolver(rpc)
        tx = create_mock_transaction()
        res = resolver.estimate_network_fees(tx)
        assert res["fee_estimation_status"] == "UNAVAILABLE"

    def test_fee_cap_exceeded_preserves_estimate(self):
        samples = [{"prioritizationFee": 100_000_000}]
        rpc = MockRpcClient(samples)
        resolver = FeeResolver(rpc)
        
        tx = create_mock_transaction(cu_limit=200_000)
        res = resolver.estimate_network_fees(tx, fee_cap_sol=0.005)
        
        assert res["fee_estimation_status"] == "COMPLETE"
        # Total priority fee in lamports = 100_000_000
        assert res["priority_fee_lamports"] == 100_000_000.0
        assert res["total_network_fee_lamports"] == 100_005_000.0
        assert res["compute_unit_price_micro_lamports"] == 500_000_000.0
        assert res["fee_cap_lamports"] == 5000000.0
        # It successfully estimated, the cap rejection logic is in the executor.
        
    def test_v0_address_lookup_tables(self, monkeypatch):
        rpc = MockRpcClient({"value": [{"data": ["ZHVtbXliYXNlNjQ="]}]})
        resolver = FeeResolver(rpc)
        tx = MagicMock(spec=VersionedTransaction)
        tx.message = MagicMock()
        
        lookup = MagicMock()
        lookup.account_key = Pubkey.default()
        lookup.writable_indexes = [0]
        tx.message.address_table_lookups = [lookup]
        
        # mock static keys for the loop
        tx.message.header.num_required_signatures = 1
        tx.message.header.num_readonly_signed_accounts = 0
        tx.message.header.num_readonly_unsigned_accounts = 1
        tx.message.account_keys = [Pubkey.default(), Pubkey.default(), Pubkey.default()]
        
        mock_alt = MagicMock()
        mock_alt.addresses = ["33333333333333333333333333333333"]
        resolver._deserialize_alt = lambda x: mock_alt
        
        writable = resolver.extract_writable_accounts(tx)
        
        assert "33333333333333333333333333333333" in writable
        assert rpc.called_with[0][0] == "getMultipleAccounts"
