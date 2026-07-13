#!/usr/bin/env python3
"""Entry point for the remote workflow and dataset-sink watchdog."""

import sys

from orcap.remote_health import main

if __name__ == "__main__":
    sys.exit(main())
