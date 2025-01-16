import argparse
#  Parse a --no-newline argument
parser = argparse.ArgumentParser()
parser.add_argument("--no-newline", action="store_true", default=False)
parser.add_argument("args", nargs=argparse.REMAINDER)
args = parser.parse_args()

p = " ".join(args.args)
if not args.no_newline:
    p += "\n"
print(p, end="")
