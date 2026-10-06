"""
Unified Entry Point for RAW to PNG Converter.
Launches the GUI desktop application by default, or the CLI tool when arguments are provided.
"""

import sys
import os

# Add script directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    # If no arguments provided, or specifically requested GUI, launch GUI
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1].lower() in ["--gui", "-g"]):
        try:
            from gui import main as launch_gui
            launch_gui()
        except ImportError as e:
            print(f"Error loading GUI: {e}", file=sys.stderr)
            print("Falling back to CLI mode...")
            from cli import main_cli
            sys.exit(main_cli(["--help"]))
    else:
        from cli import main_cli
        # Filter out '--cli' flag if passed explicitly
        filtered_args = [arg for arg in sys.argv[1:] if arg != "--cli"]
        sys.exit(main_cli(filtered_args))


if __name__ == "__main__":
    main()
