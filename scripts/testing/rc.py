# Read first argument from command line, convert to integer.
# If the argument isn't an integer, exit with 1.
# If it is between 1 and 255, exit with that code. Otherwise, exit with 1.

import sys
import random

rc = -1
if len(sys.argv) > 1:
    try:
        rc = int(sys.argv[1])
    except ValueError:
        ...

if rc < 0 or rc > 255:
    #  create a random number between 1 and 255
    rc = random.randint(0, 255)

sys.exit(rc)
