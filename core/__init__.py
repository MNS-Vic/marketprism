"""
🚀 MarketPrism Core
This file is intentionally kept minimal to avoid circular import issues.
Sub-modules should be imported from directly.

Example:
Instead of: from core import UnifiedSessionManager
Use: from core.networking.unified_session_manager import UnifiedSessionManager
"""

# This file is intentionally left mostly blank.

from datetime import datetime, timezone
import pkgutil

# Allow other parts of the system to extend the 'core' namespace package.
# This is crucial for allowing tests and services to correctly resolve
# modules within the core package, especially in complex project structures.
__path__ = pkgutil.extend_path(__path__, __name__)
