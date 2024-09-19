# Read first argument from command line, convert to integer.
# If the argument isn't an integer, exit with 1.
# If it is between 1 and 255, exit with that code. Otherwise, exit with 1.

import sys

arg = sys.argv[1]
try:
    arg = int(arg)
except ValueError:
    sys.exit(1)

if 0 <= arg <= 255:
    sys.exit(arg)
else:
    sys.exit(1)
