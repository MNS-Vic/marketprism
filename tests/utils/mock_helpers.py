"""
Mock Helpers for MarketPrism Testing

This module provides mock objects for external services like NATS,
allowing for isolated integration testing without requiring a live environment.
"""

from datetime import datetime, timezone
import asyncio
from typing import Dict, Any, List

class MockNATSClient:
    def __init__(self):
        self.published_messages: List[Dict[str, Any]] = []

    async def publish(self, subject: str, payload: bytes):
        self.published_messages.append({
            'subject': subject,
            'payload': payload,
        })
        await asyncio.sleep(0) # Simulate async operation

    async def connect(self, *args, **kwargs):
        pass

    async def close(self, *args, **kwargs):
        pass

class MockNATSServer:
    """A mock NATS server to simulate a NATS connection for tests."""
    def __init__(self):
        self.client = MockNATSClient()

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass 