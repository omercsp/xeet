# Description: read an input integer 'repeat' and an input integer 'period'.
# The would repeat the input integer 'repeat':
# - Write randomly to stdout or stderr. For stdout write "<LINENO> stdout" and for stderr
#   write "<LINENO> stderr", where <LINENO> is the line number of the output.
# - Sleep for 'period' seconds.

import sys
import argparse
import random
import time

parser = argparse.ArgumentParser()
parser.add_argument("repeat", type=int, help="The number of times to repeat")
parser.add_argument("period", type=float, help="The number of seconds to sleep")
args = parser.parse_args()
for i in range(args.repeat):
    if random.choice([True, False]):
        print(f"{i} stdout")
        sys.stdout.flush()
    else:
        print(f"{i} stderr", file=sys.stderr)
        sys.stderr.flush()
        #  sys.stderr.write(f"{i} stderr\n")
    time.sleep(args.period)
