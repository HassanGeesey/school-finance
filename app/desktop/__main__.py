"""Run the desktop launcher via ``python -m app.desktop`` (dev convenience)."""

import sys

from .launcher import main

sys.exit(main())
