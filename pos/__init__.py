"""Point of Sale system (Electronics POS / Shop POS editions)."""
from .edition import current as _edition

__version__ = "1.3.0"
APP_NAME = _edition()["app_name"]
