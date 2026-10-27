"""Timestamp parsing shared by live evidence without importing UI monitoring."""
from datetime import datetime
import re
def parse_callback_time(value):
    return datetime.fromisoformat(re.sub(r'(\.\d{6})\d+(?=[+-]\d{2}:\d{2}$)',r'\1',value.replace('Z','+00:00')))
