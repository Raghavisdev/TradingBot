import time
import logging

from solders.transaction import VersionedTransaction

logger = logging.getLogger("FeeResolver")


class FeeResolver:
    def __init__(self, rpc_client):
        """
        Initializes the FeeResolver.
        :param rpc_client: A client with an `_rpc(method, params)` interface (e.g., SolanaSender).
        """
        self.rpc_client = rpc_client

    def extract_writable_accounts(self, transaction: VersionedTransaction) -> list:
        """
        Extracts writable account addresses from the transaction.
        """
        message = transaction.message
        header = message.header
        
        num_required_sigs = header.num_required_signatures
        num_readonly_signed = header.num_readonly_signed_accounts
        num_readonly_unsigned = header.num_readonly_unsigned_accounts
        account_keys = message.account_keys
        num_accounts = len(account_keys)
        
        # Writable signed accounts
        num_writable_signed = num_required_sigs - num_readonly_signed
        writable_signed = account_keys[0:num_writable_signed]
        
        # Writable unsigned accounts
        num_writable_unsigned = num_accounts - num_required_sigs - num_readonly_unsigned
        writable_unsigned = account_keys[num_required_sigs:num_required_sigs + num_writable_unsigned]
        
        writable_accounts = list(writable_signed) + list(writable_unsigned)
        
        # Address Lookup Tables handling for VersionedTransaction (v0)
        if hasattr(message, "address_table_lookups") and message.address_table_lookups:
            table_pubkeys = [str(lookup.account_key) for lookup in message.address_table_lookups]
            try:
                rpc_response = self.rpc_client._rpc(
                    "getMultipleAccounts",
                    [table_pubkeys, {"encoding": "base64"}]
                )
                if isinstance(rpc_response, dict) and "value" in rpc_response:
                    accounts_data = rpc_response["value"]
                    for idx, lookup in enumerate(message.address_table_lookups):
                        acc = accounts_data[idx]
                        if acc and acc.get("data"):
                            import base64
                            raw_data = base64.b64decode(acc["data"][0])
                            alt = self._deserialize_alt(raw_data)
                            for w_idx in lookup.writable_indexes:
                                if w_idx < len(alt.addresses):
                                    writable_accounts.append(alt.addresses[w_idx])
            except Exception as e:
                logger.warning(f"Failed to resolve address lookup tables: {e}")
                
        return [str(pk) for pk in writable_accounts]

    def _deserialize_alt(self, raw_data):
        from solders.address_lookup_table_account import AddressLookupTable
        return AddressLookupTable.deserialize(raw_data)

    def extract_compute_unit_limit(self, transaction: VersionedTransaction):
        """
        Parses the SetComputeUnitLimit instruction from the ComputeBudget program.
        If missing or malformed, returns None.
        """
        message = transaction.message
        account_keys = message.account_keys
        
        COMPUTE_BUDGET_PROGRAM_ID = "ComputeBudget111111111111111111111111111111"
        
        limit = None
        for instruction in message.instructions:
            program_id_index = instruction.program_id_index
            program_id = str(account_keys[program_id_index])
            
            if program_id == COMPUTE_BUDGET_PROGRAM_ID:
                data = instruction.data
                if len(data) >= 5 and data[0] == 2:  # SetComputeUnitLimit
                    current_limit = int.from_bytes(data[1:5], "little")
                    if limit is None:
                        limit = current_limit
                    else:
                        # Ambiguous: multiple limits
                        return None
                        
        return limit

    def estimate_network_fees(self, transaction: VersionedTransaction, fee_cap_sol: float = 0.005) -> dict:
        """
        Estimates the network fee by querying the RPC for recent prioritization fees.
        """
        try:
            num_signatures = transaction.message.header.num_required_signatures
            base_fee_lamports = float(5000 * num_signatures)
        except Exception as e:
            logger.error(f"Failed to extract base fee: {e}")
            return {"fee_estimation_status": "UNAVAILABLE", "fee_source": "UNAVAILABLE"}

        try:
            compute_unit_limit = self.extract_compute_unit_limit(transaction)
            if compute_unit_limit is None:
                logger.error("Failed to parse Compute Unit Limit. Missing or malformed.")
                return {"fee_estimation_status": "UNAVAILABLE", "fee_source": "UNAVAILABLE"}
        except Exception as e:
            logger.error(f"Error parsing CU limit: {e}")
            return {"fee_estimation_status": "UNAVAILABLE", "fee_source": "UNAVAILABLE"}
            
        try:
            writable_accounts = self.extract_writable_accounts(transaction)
        except Exception as e:
            logger.error(f"Error parsing writable accounts: {e}")
            return {"fee_estimation_status": "UNAVAILABLE", "fee_source": "UNAVAILABLE"}
            
        try:
            rpc_response = self.rpc_client._rpc("getRecentPrioritizationFees", [writable_accounts])
            if not isinstance(rpc_response, list):
                raise ValueError("RPC did not return a list of fees")
        except Exception as e:
            logger.error(f"RPC getRecentPrioritizationFees failed: {e}")
            return {"fee_estimation_status": "UNAVAILABLE", "fee_source": "UNAVAILABLE"}
            
        try:
            samples = [item["prioritizationFee"] for item in rpc_response if isinstance(item, dict) and "prioritizationFee" in item]
            non_zero_samples = [fee for fee in samples if fee > 0]
            
            if not non_zero_samples:
                compute_unit_price = 0.0
                priority_fee_lamports = 0.0
            else:
                non_zero_samples.sort()
                n = len(non_zero_samples)
                index = (n - 1) * 0.75
                lower_idx = int(index)
                upper_idx = min(lower_idx + 1, n - 1)
                weight = index - lower_idx
                # Priority fee is explicitly treated as lamports as mandated by dimensional audit
                priority_fee_lamports = float(non_zero_samples[lower_idx] * (1 - weight) + non_zero_samples[upper_idx] * weight)
                # Compute micro-lamports per CU from total lamports
                compute_unit_price = (priority_fee_lamports * 1_000_000.0) / compute_unit_limit
                
            total_network_fee_lamports = base_fee_lamports + priority_fee_lamports
            
        except Exception as e:
            logger.error(f"Fee calculation failed: {e}")
            return {"fee_estimation_status": "UNAVAILABLE", "fee_source": "UNAVAILABLE"}
            
        fee_cap_lamports = float(fee_cap_sol * 1_000_000_000)
        
        return {
            "base_fee_lamports": base_fee_lamports,
            "priority_fee_lamports": priority_fee_lamports,
            "total_network_fee_lamports": total_network_fee_lamports,
            "compute_unit_limit": int(compute_unit_limit),
            "compute_unit_price_micro_lamports": compute_unit_price,
            "fee_source": "RPC_RECENT_PRIORITIZATION_P75",
            "fee_estimation_status": "COMPLETE",
            "fee_cap_lamports": fee_cap_lamports,
            "fee_estimation_timestamp": time.time()
        }
