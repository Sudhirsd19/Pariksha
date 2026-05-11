import time
from datetime import datetime

class HealthMonitor:
    def __init__(self, stale_threshold=5.0):
        self.last_tick_time = time.time()
        self.stale_threshold = stale_threshold
        self.is_connected = False
        self.api_failures = 0
        self.max_api_failures = 5

    def update_tick(self):
        self.last_tick_time = time.time()
        self.is_connected = True

    def is_feed_healthy(self):
        if not self.is_connected:
            return False
        elapsed = time.time() - self.last_tick_time
        return elapsed < self.stale_threshold

    def record_api_failure(self):
        self.api_failures += 1

    def reset_api_failures(self):
        self.api_failures = 0

    def should_circuit_break(self):
        return self.api_failures >= self.max_api_failures

health_monitor = HealthMonitor()
