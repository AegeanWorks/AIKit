#!/usr/bin/env python3
"""AIKit entry point: `python aikit.py --help`. The commands live in scripts/aikit_cli.py."""

import sys

if __name__ == "__main__":
    # Top-level help is a generated, test-checked string. Printing it loads no argparse and no
    # command module, so the help path stays under the startup budget (PRINCIPLE-010 R5, ADR-180).
    # Subcommand help and real commands fall through to main(), which builds the full parser.
    if sys.argv[1:2] in (["-h"], ["--help"]):
        from scripts.aikit_help import TOP_LEVEL_HELP
        print(TOP_LEVEL_HELP, end="")
        sys.exit(0)
    from scripts.aikit_cli import main
    sys.exit(main())
