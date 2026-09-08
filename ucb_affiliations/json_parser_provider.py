"""
Custom flowtoy provider for parsing JSON strings.
"""
import json
from typing import Any, Dict, Optional


class JsonParserProvider:
    """Provider that parses JSON from a string input."""
    
    type_name = "json_parser"
    
    def __init__(self, configuration: Dict[str, Any]):
        self.configuration = configuration or {}
    
    def call(self, input_payload: Optional[Any] = None) -> Any:
        """Parse JSON from input string and return the parsed data."""
        try:
            # input_payload should be a JSON string
            if isinstance(input_payload, str):
                parsed_data = json.loads(input_payload)
            else:
                # If it's already parsed, just return it
                parsed_data = input_payload
            
            return {
                'status': {
                    'success': True,
                    'code': 0,
                    'notes': []
                },
                'data': parsed_data,
                'meta': {}
            }
        except (json.JSONDecodeError, TypeError) as e:
            return {
                'status': {
                    'success': False,
                    'code': 1,
                    'notes': [f'JSON parsing failed: {str(e)}']
                },
                'data': {},
                'meta': {}
            }
