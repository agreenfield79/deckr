"""
limiter.py — Shared slowapi Limiter instance (Step 30.3).

Defined here (not in main.py) to avoid circular imports when routers
import the limiter for @limiter.limit() decorators.

Usage:
    from services.limiter import limiter
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
