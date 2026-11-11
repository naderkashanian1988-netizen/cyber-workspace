"""PyInstaller entry point for CYBER WORKSPACE (Windows host)."""

import sys

from cyber_workspace.app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
