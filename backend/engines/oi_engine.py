import pandas as pd
import time

class OIEngine:
    def __init__(self):
        # We will cache the Open Interest data here
        self.options_chain = {}
        self.last_update_time = 0
        
    def is_data_fresh(self, max_age_seconds=120):
        # Fix OI-4: Check if data is stale
        return (time.time() - self.last_update_time) < max_age_seconds

    def fetch_options_chain(self, symbol, smart_api):
        """
        Fetch options chain data around ATM strike dynamically using smart_api.
        """
        if not smart_api or not hasattr(smart_api, "getMarketData"):
            return
            
        from backend.utils.token_manager import token_manager
        
        idx_token = token_manager.get_token(symbol)
        idx_exch = token_manager.get_exchange(symbol)
        
        try:
            ltp_res = smart_api.ltpData(idx_exch, symbol, idx_token)
            if ltp_res and ltp_res.get('status') and ltp_res.get('data'):
                index_ltp = float(ltp_res['data']['ltp'])
            else:
                return
        except Exception as e:
            print(f"[OIEngine] Error fetching index LTP for {symbol}: {e}")
            return

        interval = 50 if symbol == "NIFTY" else 100
        atm_strike = int(round(index_ltp / interval) * interval)
        # Fix OI-3: Revert to 11 strikes for accurate PCR (we can safely fetch up to 22 NFO tokens)
        strikes = [atm_strike + i * interval for i in range(-5, 6)] # 11 strikes around ATM
        
        tokens_to_fetch = []
        token_metadata = {} # Map token -> (strike, type)
        
        for strike in strikes:
            for opt_type in ["CE", "PE"]:
                contracts = token_manager.options_index.get(symbol, {}).get(opt_type, {}).get(strike, [])
                if contracts:
                    nearest = contracts[0]
                    tok = nearest["token"]
                    tokens_to_fetch.append(tok)
                    token_metadata[tok] = {"strike": strike, "type": opt_type}
                    
        if not tokens_to_fetch:
            return

        try:
            # Angel One limits NFO getMarketData token list count to 50
            exchangeTokens = {"NFO": tokens_to_fetch[:50]}
            res = smart_api.getMarketData("FULL", exchangeTokens)
            if res and res.get('status') and res.get('data'):
                data_list = res.get('data', {}).get('fetched', [])
                
                chain_data = []
                for item in data_list:
                    tok = item.get('symbolToken')
                    if tok in token_metadata:
                        meta = token_metadata[tok]
                        oi = int(item.get("opnInterest", 0))
                        chain_data.append({
                            "strike": meta["strike"],
                            "type": meta["type"],
                            "oi": oi
                        })
                
                formatted_chain = {}
                for cd in chain_data:
                    stk = cd["strike"]
                    if stk not in formatted_chain:
                        formatted_chain[stk] = {"ce_oi": 0, "pe_oi": 0}
                    if cd["type"] == "CE":
                        formatted_chain[stk]["ce_oi"] = cd["oi"]
                    else:
                        formatted_chain[stk]["pe_oi"] = cd["oi"]
                        
                self.options_chain[symbol] = [
                    {"strike": stk, "ce_oi": val["ce_oi"], "pe_oi": val["pe_oi"]}
                    for stk, val in formatted_chain.items()
                ]
                self.last_update_time = time.time()
                print(f"[OIEngine] Updated options chain for {symbol}. PCR: {self.calculate_pcr(symbol)}")
        except Exception as e:
            print(f"[OIEngine] Error fetching options chain market data for {symbol}: {e}")

    def calculate_pcr(self, symbol):
        """
        Calculate Put-Call Ratio (PCR).
        PCR > 1.0 => Bullish
        PCR < 0.8 => Bearish
        """
        if symbol not in self.options_chain or not self.options_chain[symbol]:
            # No data available. Do not guess or generate random noise.
            return None

        chain_data = self.options_chain[symbol]
        total_ce_oi = sum([strike.get('ce_oi', 0) for strike in chain_data])
        total_pe_oi = sum([strike.get('pe_oi', 0) for strike in chain_data])

        if total_ce_oi == 0:
            return 1.0
        
        pcr = total_pe_oi / total_ce_oi
        return round(pcr, 2)

    def calculate_max_pain(self, symbol):
        """
        Calculate the Max Pain strike price (where options buyers lose maximum money).
        """
        if symbol not in self.options_chain or not self.options_chain[symbol]:
            return 0.0
        
        chain_data = self.options_chain[symbol]
        strikes = [s.get('strike') for s in chain_data]
        if not strikes:
            return 0.0
            
        min_pain = float('inf')
        max_pain_strike = strikes[0]
        
        for exp_strike in strikes:
            total_pain = 0.0
            for opt in chain_data:
                strike = opt['strike']
                ce_oi = opt.get('ce_oi', 0)
                pe_oi = opt.get('pe_oi', 0)
                
                # CE pain: option buyer loses intrinsic value if expiry strike is above strike
                if exp_strike > strike:
                    total_pain += (exp_strike - strike) * ce_oi
                # PE pain: option buyer loses intrinsic value if expiry strike is below strike
                elif exp_strike < strike:
                    total_pain += (strike - exp_strike) * pe_oi
                    
            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = exp_strike
                
        return float(max_pain_strike)

    def is_oi_supportive(self, symbol, side, current_price=None):
        """
        Checks if the Open Interest supports the trade direction.
        Used as a final filter before placing a trade.
        """
        # Fix OI-4: Stale check
        if not self.is_data_fresh():
            print(f"[OIEngine] Stale OI data (>{120}s old). Allowing trade.")
            return True
            
        pcr = self.calculate_pcr(symbol)
        
        # Fail-Safe: If PCR couldn't be calculated, assume Neutral and don't block the trade.
        if pcr is None:
            return True
            
        # Fix OI-2: Wire Max Pain filter
        # BUG #8 FIX: Old code had INVERTED logic:
        #   - Blocked BUY when price > max_pain (backwards: above max pain = gravitational pull DOWN, not a BUY block)
        #   - Blocked SELL when price < max_pain (backwards: below max pain = gravitational pull UP, not a SELL block)
        # Correct behavior: only block when PINNED to max pain (within 0.1%)
        if current_price:
            max_pain = self.calculate_max_pain(symbol)
            if max_pain > 0:
                distance_pct = abs(current_price - max_pain) / current_price * 100
                # Only block when price is PINNED very close to max pain (magnetic zone)
                if distance_pct < 0.1:
                    print(f"[OIEngine] Price pinned at max pain ({max_pain}). High magnetism. Skipping {side}.")
                    return False
                # Informational warning only (not a block)
                if distance_pct < 0.5:
                    print(f"[OIEngine] Price near max pain ({max_pain}, {distance_pct:.2f}% away). Trade with caution.")
            
        # Fix OI-1: Asymmetric thresholds & Weekly Expiry Adjustment
        import datetime
        now_ist = datetime.datetime.now()
        EXPIRY_DAY = now_ist.weekday() == 3  # Thursday = NSE weekly expiry
        
        if side == "BUY":
            threshold = 0.65 if EXPIRY_DAY else 0.75
            if pcr < threshold:
                print(f"[OIEngine] TRAP ALERT: Rejecting BUY on {symbol}. PCR is too low ({pcr}). Call writers dominate.")
                return False
        elif side == "SELL":
            threshold = 1.35 if EXPIRY_DAY else 1.25
            if pcr > threshold:
                print(f"[OIEngine] TRAP ALERT: Rejecting SELL on {symbol}. PCR is too high ({pcr}). Put writers dominate.")
                return False
                
        return True

oi_engine = OIEngine()
