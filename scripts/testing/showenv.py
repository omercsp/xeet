import sys
import os

if len(sys.argv) != 2:
    sys.exit(0)

arg = sys.argv[1]
print(os.environ.get(arg, ""))
