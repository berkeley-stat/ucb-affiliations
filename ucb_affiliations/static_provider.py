"""
Custom flowtoy provider for static data injection.
"""
from typing import Any, Dict, Optional


class StaticDataProvider:
    """Provider that returns pre-configured static data."""
    
    type_name = "static"
    
    def __init__(self, configuration: Dict[str, Any]):
        self.configuration = configuration or {}
        self.data = self.configuration.get('data', {})
    
    def call(self, input_payload: Optional[Any] = None) -> Any:
        """Return the static data as a successful result."""
        return {
            'status': {
                'success': True,
                'code': 0,
                'notes': []
            },
            'data': self.data,
            'meta': {}
        }
