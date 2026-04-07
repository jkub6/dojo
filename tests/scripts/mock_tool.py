import os
import sys

if __name__ == "__main__":
    exit_code = int(os.environ.get("MOCK_TOOL_EXIT", "0"))
    stdout = os.environ.get("MOCK_TOOL_STDOUT", "")
    stderr = os.environ.get("MOCK_TOOL_STDERR", "")
    arg_to_print = os.environ.get("MOCK_TOOL_PRINT_ARG", "")

    if stdout:
        sys.stdout.write(stdout + "\n")
    if stderr:
        sys.stderr.write(stderr + "\n")

    if arg_to_print:
        # If specified, print matching arguments
        for arg in sys.argv:
            if arg_to_print in arg:
                sys.stdout.write(f"Argument found: {arg}\n")

    sys.exit(exit_code)
