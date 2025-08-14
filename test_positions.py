#!/usr/bin/env python3
"""Simple test to isolate the positions repository issue"""

import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from backend.infra.db import get_session  
from backend.infra.repositories import get_portfolio_repo

async def test_positions_repo():
    try:
        # Get session generator
        session_gen = get_session()
        session = await session_gen.__anext__()
        
        # Get repo
        repo = get_portfolio_repo(session)
        print(f"Repository type: {type(repo)}")
        
        # Test the method
        print("Testing get_all_positions...")
        result = await repo.get_all_positions()
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")
        
        await session_gen.__anext__()  # Close session
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_positions_repo())
