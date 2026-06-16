import yfinance as yf
import pandas as pd

data = yf.download("RELIANCE.NS", period="60d", interval="5m", progress=False)
if isinstance(data.columns, pd.MultiIndex):
    data.columns = [col[0] for col in data.columns]

df = data.reset_index()
df.columns = ['date', 'close', 'high', 'low', 'open', 'volume']

# Check hour distribution
hours = pd.to_datetime(df['date']).dt.hour
print("Hour distribution in data:")
print(hours.value_counts().sort_index())
print(f"\nHour range: {hours.min()} to {hours.max()}")
print(f"Total hours covered: {hours.nunique()}")

# Check how many rows in each restricted window
allowed_hours = [(10, 11), (14, 15)]
total_allowed = 0
for h_start, h_end in allowed_hours:
    count = ((hours >= h_start) & (hours < h_end)).sum()
    total_allowed += count
    print(f"Rows in {h_start:02d}:00-{h_end:02d}:00: {count}")

print(f"Total allowed rows: {total_allowed} / {len(df)}")
