#  Read a float from the command line, sleep for that many seconds, then exit with 0.

import sys
import time

seconds: float = 1
if len(sys.argv) == 2:
    try:
        seconds = float(sys.argv[1])
    except ValueError:
        print("Invalid number of seconds, defaulting to 1")

time.sleep(seconds)
sys.exit(0)
