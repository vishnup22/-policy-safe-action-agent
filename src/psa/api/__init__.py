"""HTTP adapter. Runtime wiring is injected through the frozen ports."""

from psa.api.app import create_app
from psa.api.auth import Settings

__all__ = ["Settings", "create_app"]
