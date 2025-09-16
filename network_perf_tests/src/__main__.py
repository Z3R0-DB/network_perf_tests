import sys
from cli import main as cli_main

if __name__ == "__main__":
    try:
        cli_main()
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)