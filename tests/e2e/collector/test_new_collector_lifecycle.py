from datetime import datetime, timezone
import pytest
import asyncio
import os
import sys
from pathlib import Path
import logging

# Setup paths
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "services" / "python-collector" / "src"))

from marketprism_collector.collector import MarketDataCollector
from marketprism_collector.config import Config

# Configure basic logging for tests
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@pytest.mark.asyncio
async def test_collector_basic_lifecycle():
    """
    Tests the basic start-run-stop lifecycle of the new MarketDataCollector.
    This serves as a template for new E2E tests.
    """
    logger.info("Setting up minimal config for lifecycle test.")
    config_dict = {
        'exchanges': {
            'binance': {
                'name': 'binance',
                'testnet': True,
                'enabled': True,
                'symbols': ['BTCUSDT'],
                'data_types': ['ticker'] # Keep it minimal
            }
        },
        'data_collection': {
            'collection_interval': 5.0,
            'timeout': 10
        },
        'storage': {
            'nats': {
                'enabled': False # Disable NATS for this simple test
            }
        },
        'http_server': {
            'enabled': True,
            'port': 9876  # Use a unique port for testing
        }
    }

    collector = None
    try:
        logger.info("Creating Config object.")
        config = Config.from_dict(config_dict)

        logger.info("Initializing MarketDataCollector.")
        collector = MarketDataCollector(config)

        logger.info("Starting MarketDataCollector.")
        start_success = await asyncio.wait_for(collector.start(), timeout=10)
        assert start_success is True, "Collector.start() should return True on success."

        logger.info("Collector started. Running for 2 seconds.")
        await asyncio.sleep(2)

        # Check health via the HTTP endpoint
        health_status = await collector._health_handler(None)
        assert health_status.status == 200, "Health check should return status 200."
        
        logger.info("Collector is healthy.")

    finally:
        if collector:
            logger.info("Stopping MarketDataCollector.")
            await asyncio.wait_for(collector.stop(), timeout=10)
            logger.info("Collector stopped successfully.") 