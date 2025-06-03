from typing import Dict, Any, List
from dataclasses import dataclass, field

@dataclass
class ServicesConfig:
    python_collector: Dict[str, Any] = field(default_factory=lambda: {"enabled": True, "exchanges": {"okx": {"enabled": True}}})

services_config = ServicesConfig()

def get_python_collector_config():
    return services_config.python_collector

def get_enabled_exchanges():
    exchanges = services_config.python_collector.get("exchanges", {})
    return [name for name, config in exchanges.items() if config.get("enabled")]

def is_service_enabled(service_name):
    return True
