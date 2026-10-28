"""
roascan.desktop.__main__: Entry point for `python -m roascan.desktop`.
"""

import sys
from .tray_app import main

if __name__ == "__main__":
    sys.exit(main())
