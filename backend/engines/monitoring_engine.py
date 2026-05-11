import requests
import logging

class MonitoringEngine:
    def __init__(self, telegram_token=None, chat_id=None):
        self.telegram_token = telegram_token
        self.chat_id = chat_id
        self.critical_errors = 0

    def send_alert(self, message, level="INFO"):
        """Send urgent alerts to external channels."""
        prefix = "🔴 CRITICAL: " if level == "CRITICAL" else "🔔 INFO: "
        formatted_msg = f"{prefix}{message}"
        
        logging.info(formatted_msg)
        
        if self.telegram_token and self.chat_id:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            try:
                requests.post(url, data={"chat_id": self.chat_id, "text": formatted_msg})
            except Exception as e:
                logging.error(f"Failed to send Telegram alert: {e}")

    def track_error(self, error_type):
        """Monitor error frequency for circuit-breaking."""
        self.critical_errors += 1
        if self.critical_errors > 10:
            self.send_alert("System triggering circuit breaker due to high error rate!", "CRITICAL")
            return True # Signal for shutdown
        return False
