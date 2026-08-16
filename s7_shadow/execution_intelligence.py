import json

EXECUTION_MODEL_VERSION = 'THEORETICAL_AMM_HEURISTIC_V1'

class ExecutionIntelligence:
    @staticmethod
    def calculate_snapshot(coin, s6_allocation):
        """
        Calculates an explicitly theoretical execution-quality snapshot.
        Does NOT alter S6 decisions. Used purely for observation and future calibration.
        """
        # --- OBSERVED ---
        price = getattr(coin, 'price', 0.0)
        if price is None: price = 0.0
        
        liq = getattr(coin, 'liquidity', 0.0)
        if liq is None: liq = 0.0
        
        vol_5m = getattr(coin, 'volume_5m', 0.0)
        if vol_5m is None: vol_5m = 0.0
        
        observed = {
            "requested_allocation_usd": float(s6_allocation),
            "price_at_decision": float(price),
            "liquidity_usd": float(liq),
            "volume_5m_usd": float(vol_5m),
            "volume_1h_usd": float(getattr(coin, 'volume_1h', 0.0)),
            "buys_5m": int(getattr(coin, 'buys_5m', 0)),
            "sells_5m": int(getattr(coin, 'sells_5m', 0)),
            "chain": getattr(coin, 'chain', 'unknown'),
            "dex": getattr(coin, 'dex', 'unknown'),
            "pair": getattr(coin, 'contract', 'unknown')
        }
        
        # --- DERIVED ---
        alloc = float(s6_allocation)
        
        alloc_to_liq = float('inf') if alloc > 0 else 0.0
        if liq > 0:
            alloc_to_liq = alloc / liq
            
        alloc_to_vol_5m = float('inf') if alloc > 0 else 0.0
        if vol_5m > 0:
            alloc_to_vol_5m = alloc / vol_5m
            
        derived = {
            "allocation_to_liquidity": alloc_to_liq,
            "allocation_to_volume_5m": alloc_to_vol_5m
        }
        
        # --- ESTIMATED ---
        # The coefficients 2.0, 0.5 and the 1% base fee are heuristic assumptions.
        # This is NOT a validated slippage prediction.
        
        safe_liq = max(liq, 1.0)
        safe_vol = max(vol_5m, 1.0)
        
        base_fee = 0.01  # 1% standard dex fee heuristic
        
        # entry_impact = allocation / max(liquidity, 1) * 2.0 + allocation / max(volume_5m, 1) * 0.5 + base_fee(1%)
        est_entry_impact = (alloc / safe_liq * 2.0) + (alloc / safe_vol * 0.5) + base_fee
        
        # exit_impact = entry_impact * 1.5
        est_exit_impact = est_entry_impact * 1.5
        
        est_round_trip = est_entry_impact + est_exit_impact
        
        # Status heuristic
        status = "SAFE"
        if alloc_to_liq > 0.05 or alloc_to_vol_5m > 0.5:
            status = "DANGEROUS_LIQUIDITY"
        elif est_round_trip > 0.10:
            status = "HIGH_IMPACT"
            
        estimated = {
            "estimated_entry_impact": est_entry_impact,
            "estimated_exit_impact": est_exit_impact,
            "estimated_round_trip_cost": est_round_trip,
            "execution_quality_status": status
        }
        
        snapshot = {
            "execution_model_version": EXECUTION_MODEL_VERSION,
            "OBSERVED": observed,
            "DERIVED": derived,
            "ESTIMATED": estimated
        }
        
        return snapshot
