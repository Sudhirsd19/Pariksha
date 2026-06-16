import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.backtesting.run_backtest import main
import asyncio

async def debug_main():
    await main()

if __name__ == '__main__':
    asyncio.run(debug_main())
