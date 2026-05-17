"""Vercel entry point. Vercel routes /api/* to this file's `app`."""
from .server import app

__all__ = ["app"]
