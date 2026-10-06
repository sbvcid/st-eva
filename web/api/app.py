"""
Compatibility module alias to support python -m web.api.app
"""

from web.app import app, main

__all__ = ["app", "main"]

if __name__ == "__main__":
    main()

