"""Allow running the web app with `python -m web_app`."""

import sys


def main():
    try:
        from .server import main as server_main

        server_main()
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Fatal error starting web app: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
