#!/usr/bin/env python3
"""Idea Catcher entry point: `python idea_catcher.py --help`."""

import sys

from idea_catcher.registry import main

if __name__ == "__main__":
    sys.exit(main())
