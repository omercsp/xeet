from xeet.common import XeetException
from xeet.log import init_logging, log_error, log_info
from xeet.pr import disable_colors
from xeet.core import TestsCriteria
from xeet.reporters import ConsolePrinterOpts, BaseConsoleReporterOpts
from xeet.args import Args, parse_arguments, XeetCliCmds, XeetCliDumpTypes
import xeet.cli as actions
import os


def _tests_criteria(args: Args, hidden: bool) -> TestsCriteria:
    return TestsCriteria(
        names=args.tests,
        exclude_names=set(args.exclude_tests),
        fuzzy_names=args.fuzzy_tests,
        fuzzy_exclude_names=set(args.fuzzy_exclude_tests),
        include_groups=args.groups,
        require_groups=set(args.require_groups),
        exclude_groups=set(args.exclude_groups),
        abstract_tests=hidden)


def _display_settings(args: Args) -> BaseConsoleReporterOpts:
    if args.debug:
        opts = BaseConsoleReporterOpts()
        if args.run_verbosity == actions.RunVerbosity.Concise:
            opts.set_concise()
        return opts

    opts = ConsolePrinterOpts()
    if args.run_verbosity == actions.RunVerbosity.Verbose:
        opts.set_verbose()
    elif args.run_verbosity == actions.RunVerbosity.Concise:
        opts.set_concise()
    elif args.run_verbosity == actions.RunVerbosity.Quiet:
        opts.set_quiet()
    opts.set(args.display[0], args.display[1])
    return opts


def _run_settings(args: Args) -> actions.XeetRunSettings:
    #  We never run abastract and mtrix tests in run mode. We always run permutations
    criteria = _tests_criteria(args, hidden=False)
    criteria.prmttn_idxs_inc = args.permutations
    criteria.prmttn_idxs_exc = args.no_permutations
    return actions.XeetRunSettings(
        criteria=criteria,
        iterations=args.repeat,
        output_dir=args.output_dir,
        debug=args.debug,
        jobs=args.jobs,
        randomize=args.randomize)


def xrun() -> int:
    args = parse_arguments()
    if args.no_colors:
        disable_colors()

    try:
        cmd_name = args.subparsers_name
        if cmd_name == XeetCliCmds.Dump:
            if args.dump_type == XeetCliDumpTypes.Schema:
                actions.dump_schema(args.type)
            elif args.dump_type == XeetCliDumpTypes.Test:
                actions.dump_test(args.conf, args.test_name)
            elif args.dump_type == XeetCliDumpTypes.Config:
                actions.dump_config(args.conf, args.path)
            return 0
        if args.log_file:
            init_logging("Xeet", args.log_file, args.log_verbosity)
        log_info(f"running command '{args.subparsers_name}'")
        log_info(f"CWD is '{os.getcwd()}'")
        if cmd_name == XeetCliCmds.Run:
            return actions.run_tests(args.conf, _run_settings(args), _display_settings(args))
        if cmd_name == XeetCliCmds.ListTests:
            actions.list_tests(args.conf, args.names_only, _tests_criteria(args, args.all))
        elif cmd_name == XeetCliCmds.ListGroups:
            actions.list_groups(args.conf)
        elif cmd_name == XeetCliCmds.Info:
            actions.show_test_info(args.conf, _tests_criteria(args, True), args.expand, args.full)
        else:
            raise XeetException(f"Unknown command '{cmd_name}'")
        return 0

    except XeetException as e:
        # flush the stdout buffer
        log_error(f"xeet: {e}")
        return 255


if __name__ == "__main__":
    exit(xrun())
