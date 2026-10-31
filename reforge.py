#!/usr/bin/env python3
"""Standalone Aegean Reforge entry point: `python reforge.py --help`."""

import sys

from reforge.cli import main

if __name__ == "__main__":
    sys.exit(main())
