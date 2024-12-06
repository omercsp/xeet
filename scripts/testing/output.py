import sys

had_stdout = False
had_stderr = False
i = 1
while i < len(sys.argv[1:]):
    if i == len(sys.argv) - 1:
        sys.exit(1)
    if sys.argv[i] == "--stdout":
        i += 1
        print(sys.argv[i], end="", flush=True)
        had_stdout = True

    elif sys.argv[i] == "--stderr":
        i += 1
        print(sys.argv[i], file=sys.stderr, end="", flush=True)
        had_stderr = True
    else:
        print()
        sys.exit()
    i += 1
