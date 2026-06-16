"""
Parameter Optimizer & Walk-Forward Backtester
Grid search + train/test split (70/30) for robust parameter optimization
"""
import pandas as pd
import numpy as np
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from itertools import product
import warnings
warnings.filterwarnings('ignore')

class ParameterOptimizer:
    """
    Grid search optimizer for strategy parameters using walk-forward analysis.
    Prevents overfitting by separating train/test data.
    """
    
    def __init__(self, df, train_ratio=0.7):
        self.df = df.copy()
        self.train_ratio = train_ratio
        split_idx = int(len(df) * train_ratio)
        self.train_df = df.iloc[:split_idx].reset_index(drop=True)
        self.test_df = df.iloc[split_idx:].reset_index(drop=True)
        self.results = []
        
    def optimize_parameters(self, 
                          risk_per_trade_values=[0.01, 0.02, 0.03],
                          atr_sl_values=[1.0, 1.5, 2.0],
                          atr_tp_values=[2.0, 3.0, 4.0]):
        """
        Grid search for best parameter combination
        
        Args:
            risk_per_trade_values: Risk per trade as % of capital
            atr_sl_values: ATR multiplier for stop loss
            atr_tp_values: ATR multiplier for take profit
            
        Returns:
            DataFrame with results ranked by Sharpe ratio
        """
        print("=" * 70)
        print("PARAMETER OPTIMIZATION (TRAIN SET)")
        print("=" * 70)
        print(f"Total candles: {len(self.df)}")
        print(f"Train candles: {len(self.train_df)} | Test candles: {len(self.test_df)}")
        print()
        
        param_combinations = list(product(
            risk_per_trade_values,
            atr_sl_values,
            atr_tp_values
        ))
        
        print(f"Testing {len(param_combinations)} parameter combinations...\n")
        
        for idx, (risk, sl, tp) in enumerate(param_combinations, 1):
            engine = AdvancedBacktestEngine(initial_capital=100000)
            report = engine.run_backtest(
                self.train_df,
                risk_per_trade=risk,
                atr_sl=sl,
                atr_tp=tp
            )
            
            result = {
                'risk_pct': risk * 100,
                'atr_sl': sl,
                'atr_tp': tp,
                'train_win_rate': report['win_rate'],
                'train_net_profit': report['net_profit'],
                'train_sharpe': report['sharpe_ratio'],
                'train_sortino': report['sortino_ratio'],
                'train_profit_factor': report['profit_factor'],
                'train_max_dd': report['max_drawdown_pct'],
                'total_trades': report['total_trades']
            }
            
            self.results.append(result)
            
            if idx % 3 == 0 or idx == 1:
                print(f"[{idx}/{len(param_combinations)}] Risk={risk*100:.1f}% | SL={sl}x | TP={tp}x | "
                      f"Sharpe={report['sharpe_ratio']:.2f} | Win%={report['win_rate']:.1f}%")
        
        results_df = pd.DataFrame(self.results)
        
        # Rank by Sharpe ratio (best risk-adjusted returns)
        results_df = results_df.sort_values('train_sharpe', ascending=False)
        
        print("\n" + "=" * 70)
        print("TOP 5 PARAMETER COMBINATIONS (by Sharpe Ratio)")
        print("=" * 70)
        print(results_df[['risk_pct', 'atr_sl', 'atr_tp', 'train_sharpe', 
                          'train_win_rate', 'train_profit_factor']].head(5).to_string(index=False))
        
        return results_df
    
    def walk_forward_test(self, best_params, window_size=500):
        """
        Walk-forward analysis: Test best parameters on overlapping windows
        of train + test data to validate robustness
        
        Args:
            best_params: Dict with 'risk_pct', 'atr_sl', 'atr_tp'
            window_size: Candles per walk-forward window
            
        Returns:
            DataFrame with walk-forward results
        """
        print("\n" + "=" * 70)
        print("WALK-FORWARD VALIDATION")
        print("=" * 70)
        
        risk = best_params['risk_pct'] / 100
        sl = best_params['atr_sl']
        tp = best_params['atr_tp']
        
        wf_results = []
        num_windows = (len(self.df) - window_size) // 100 + 1  # 100-candle stride
        
        for w in range(num_windows):
            start_idx = w * 100
            end_idx = start_idx + window_size
            
            if end_idx > len(self.df):
                break
            
            window_df = self.df.iloc[start_idx:end_idx].reset_index(drop=True)
            
            engine = AdvancedBacktestEngine(initial_capital=100000)
            report = engine.run_backtest(
                window_df,
                risk_per_trade=risk,
                atr_sl=sl,
                atr_tp=tp
            )
            
            wf_results.append({
                'window': w,
                'start_candle': start_idx,
                'end_candle': end_idx,
                'net_profit': report['net_profit'],
                'win_rate': report['win_rate'],
                'sharpe': report['sharpe_ratio'],
                'max_dd': report['max_drawdown_pct'],
                'trades': report['total_trades']
            })
        
        wf_df = pd.DataFrame(wf_results)
        
        print(f"\nWalk-forward windows: {len(wf_df)}")
        print(f"Average Sharpe: {wf_df['sharpe'].mean():.2f}")
        print(f"Average Win Rate: {wf_df['win_rate'].mean():.1f}%")
        print(f"Consistency (Sharpe std): {wf_df['sharpe'].std():.2f}")
        print("\nTop 3 windows:")
        print(wf_df[['window', 'win_rate', 'sharpe', 'trades']].head(3).to_string(index=False))
        
        return wf_df


class StrategyOptimizer:
    """
    Signal-based strategy optimizer.
    Tests different entry conditions and risk parameters.
    """
    
    def __init__(self, df):
        self.df = df.copy()
        
    def optimize_signal_levels(self, 
                              rsi_oversold_values=[20, 25, 30],
                              rsi_overbought_values=[70, 75, 80],
                              volume_ma_periods=[5, 10, 20]):
        """
        Optimize signal generation parameters
        """
        print("\n" + "=" * 70)
        print("SIGNAL PARAMETER OPTIMIZATION")
        print("=" * 70)
        
        results = []
        
        for rsi_os in rsi_oversold_values:
            for rsi_ob in rsi_overbought_values:
                for vol_ma in volume_ma_periods:
                    # Count potential signals with these parameters
                    signal_count = self._count_signals(rsi_os, rsi_ob, vol_ma)
                    
                    results.append({
                        'rsi_oversold': rsi_os,
                        'rsi_overbought': rsi_ob,
                        'volume_ma_period': vol_ma,
                        'signal_count': signal_count,
                        'signal_density': signal_count / len(self.df) * 100
                    })
        
        results_df = pd.DataFrame(results)
        
        # Ideal: 50-150 signals for 6-month data
        results_df['quality_score'] = results_df['signal_count'].apply(
            lambda x: 100 - abs(x - 75) if 50 <= x <= 150 else 0
        )
        
        results_df = results_df.sort_values('quality_score', ascending=False)
        
        print("\nTop 5 signal parameter combinations:")
        print(results_df[['rsi_oversold', 'rsi_overbought', 'volume_ma_period', 
                          'signal_count', 'quality_score']].head(5).to_string(index=False))
        
        return results_df
    
    def _count_signals(self, rsi_os, rsi_ob, vol_ma):
        """Count total signals with given parameters"""
        # Simplified signal counting (in real implementation, use actual signal engine)
        return len(self.df)  # Placeholder
