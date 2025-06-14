"""
This is the top-level conftest.py for the MarketPrism project.

Pytest plugins that affect the entire test suite should be defined here.
"""

# According to pytest 7.x+, pytest_plugins should be defined in a top-level conftest
pytest_plugins = ["pytest_asyncio"]

import sys
from pathlib import Path

# Add project root to the Python path
# This ensures that absolute imports like 'from core....' work correctly
# from anywhere within the project during test execution.
sys.path.insert(0, str(Path(__file__).parent)) 