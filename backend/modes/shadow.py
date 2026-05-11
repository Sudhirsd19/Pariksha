import time
import logging
import random

class ShadowEngine:
    def __init__(self):
        self.stats = {"expected_fills": [], "simulated_fills": [], "slippage_log": []}

    def simulate_fill(self, target_price, side, volatility_atr):
        """Phase 4: Realistic Paper Trading with Slippage & Latency."""
        # Simulated Latency (50ms - 200ms)
        latency_delay = random.uniform(0.05, 0.2)
        time.sleep(latency_delay)

        # Simulated Slippage (ATR based + random noise)
        slippage = (volatility_atr * 0.1) * random.uniform(0.5, 1.5)
        
        if side == "BUY":
            fill_price = target_price + slippage
        else:
            fill_price = target_price - slippage

        execution_delta = abs(fill_price - target_price)
        self.stats["slippage_log"].append(execution_delta)
        
        return fill_price, execution_delta

class StabilityValidator:
    def __init__(self):
        self.start_time = time.time()
        self.heartbeat_logs = []

    def log_heartbeat(self, queue_size, memory_usage):
        """Monitor for memory leaks or async queue bottlenecks."""
        uptime = time.time() - self.start_time
        self.heartbeat_logs.append({
            "uptime": uptime,
            "queue_depth": queue_size,
            "mem_mb": memory_usage
        })
        
        if queue_size > 100:
            logging.warning(f"STABILITY ALERT: Async Queue Pressure High ({queue_size} items)")

    def generate_health_report(self):
        """Produce final stability and execution quality analytics."""
        return {
            "uptime_seconds": time.time() - self.start_time,
            "avg_queue_depth": sum(h['queue_depth'] for h in self.heartbeat_logs) / len(self.heartbeat_logs),
            "peak_mem_usage": max(h['mem_mb'] for h in self.heartbeat_logs)
        }
