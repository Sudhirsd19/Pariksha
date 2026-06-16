"""
Simple Test Signal Engine for debugging
Generates one signal every 100 candles for testing
"""
import pandas as pd
import numpy as np

class TestSignalEngine:
    """
    Simple signal generation for testing - generates signals every 100 candles
    """
    
    def generate_signals(self, df):
        """Generate simple test signals"""
        df = df.copy()
        df['signal'] = None
        
        # Generate one buy signal every 100 candles (simplified)
        for i in range(100, len(df), 100):
            if i % 200 == 0:
                df.at[i, 'signal'] = 'BUY'
            else:
                df.at[i, 'signal'] = 'SELL'
        
        return df
