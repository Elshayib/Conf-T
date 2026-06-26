#!/usr/bin/env python3
import sys
from conf_t.cli import ConfTCLI

def main():
    try:
        app = ConfTCLI()
        app.run()
    except (KeyboardInterrupt, SystemExit):
        print("\nExiting Conf T...")
        sys.exit(0)

if __name__ == "__main__":
    main()
