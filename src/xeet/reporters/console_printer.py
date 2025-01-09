from xeet.reporters.console import ConsoleReporterVerbosity, BaseConsoleReporterOpts
from xeet.core.events import LockableEventReporter
from xeet.common import locked
from xeet.pr import *
from xeet.core.test import TestPrimaryStatus, TestResult, TestStatus, TestSecondaryStatus, Test
from xeet.common import short_str, underline
from xeet.core.result import TestPrimaryStatus, StatusTestsDict
from rich.live import Live
from rich.markup import escape as rich_escape
from dataclasses import dataclass, field
from functools import cache


_ITERATION_COLOR = "medium_orchid"

_STATUS_COLORS = {
    TestPrimaryStatus.NotRun: "orange1",
    TestPrimaryStatus.Failed: "red",
    TestPrimaryStatus.Passed: "green",
    TestPrimaryStatus.Skipped: "grey53",
}


def _status_color(status: TestPrimaryStatus) -> str:
    return _STATUS_COLORS.get(status, XColors.NoColor)


@dataclass
class ConsolePrinterOpts(BaseConsoleReporterOpts):
    header: bool = True
    criteria: bool = False
    pre_run_tests_list: bool = True
    tests: bool = True
    result_details: bool = True
    test_timing: bool = False
    full_timing: bool = False
    ongoing: bool = True
    summary: bool = True
    iteration_summary: bool = False
    detailed_summary: bool = True
    threads_header: bool = False

    @property
    def is_verbose(self) -> bool:
        return self._verbosity == ConsoleReporterVerbosity.Verbose

    def set_verbose(self):
        super().set_verbose()
        self.criteria = True
        self.pre_run_tests_list = True
        self.iteration_summary = True
        self.test_timing = True
        self.threads_header = True

    def set_concise(self):
        super().set_concise()
        self.header = False
        self.pre_run_tests_list = False
        self.result_details = False
        self.detailed_summary = False

    def set_quiet(self):
        super().set_quiet()
        self.header = False
        self.pre_run_tests_list = False
        self.summary = False
        self.tests = False
        self.result_details = False
        self.ongoing = False
        self.threads_header = False

    @classmethod
    @cache
    def components(cls) -> set[str]:
        return set(k for k in cls.__dataclass_fields__.keys() if not k.startswith("_") and k !=
                   "test_timing_type")

    def set(self, show: list[str], hide: list[str]) -> None:
        for c in show:
            if c in self.components():
                setattr(self, c, True)
        for c in hide:
            if c in self.components():
                setattr(self, c, False)


@dataclass
class ConsolePrinter(LockableEventReporter):
    live: Live = None  # type: ignore
    display: ConsolePrinterOpts = field(default_factory=ConsolePrinterOpts)

    curr_tests: list[str] = field(default_factory=list)

    def _print_curr_tests(self) -> None:
        if not self.display.ongoing:
            return
        if self.curr_tests:
            self.live.update(f"Running: {', '.join(self.curr_tests)}")
        else:
            self.live.update("")

    def on_run_start(self, **_) -> None:
        if not self.display.header:
            return
        title = colorize_str("Starting Xeet", XColors.Bold)
        pr_info(f"\n{underline(title)}")
        self._print_criteria()
        if self.display.pre_run_tests_list:
            if self.tests:
                pr_info("Running tests: {}\n".format(", ".join([x.name for x in self.tests])))
            else:
                pr_info("No tests to run\n")
        if self.display.threads_header:
            pr_info(f"Threads: {self.threads} per iteration\n")

    def _print_criteria(self) -> None:
        if not self.display.criteria:
            return
        assert self.run_res is not None
        criteria = self.run_res.criteria

        if criteria.empty and not self.display.is_verbose:
            pr_info("No test criteria specified. All tests will be run.")
            return
        lines = ["Test criteria"]
        if self.display.is_verbose and criteria.empty:
            lines[0] += " (No test criteria specified. All tests will be run)"
        lines[0] += ":"
        if self.display.is_verbose or criteria.names:
            filter_str = ", ".join(sorted(criteria.names)) if criteria.names else "<none>"
            lines.append(f"Explicity included tests - {filter_str}")

        if self.display.is_verbose or criteria.exclude_names:
            filter_str = ", ".join(sorted(criteria.exclude_names)) if criteria.exclude_names else \
                "<none>"
            lines.append(f"Included groups - {filter_str}")

        if self.display.is_verbose or criteria.fuzzy_names:
            filter_str = ", ".join(sorted(criteria.fuzzy_names)) if criteria.fuzzy_names \
                else "<none>"
            lines.append(f"Fuzzy included tests - {filter_str}")

        if self.display.is_verbose or criteria.fuzzy_exclude_names:
            filter_str = ", ".join(sorted(criteria.fuzzy_exclude_names)) \
                if criteria.fuzzy_exclude_names else "<none>"
            lines.append(f"Explicity excluded tests - {filter_str}")

        if self.display.is_verbose or criteria.fuzzy_exclude_names:
            filter_str = ", ".join(sorted(criteria.fuzzy_exclude_names)) \
                if criteria.fuzzy_exclude_names else "<none>"
            lines.append(f"Fuzzy excluded tests - {filter_str}")

        if self.display.is_verbose or criteria.include_groups:
            filter_str = ", ".join(sorted(criteria.include_groups)) if criteria.include_groups \
                else "<none>"
            lines.append(f"Excluded groups - {filter_str}")

        if self.display.is_verbose or criteria.require_groups:
            filter_str = ", ".join(sorted(criteria.exclude_groups)) if criteria.exclude_groups \
                else "<none>"
            lines.append(f"Required groups - {filter_str}")

        pr_info("\n".join(lines) + "\n")

    @locked
    def on_test_start(self, test: Test) -> None:
        self.curr_tests.append(test.name)
        self._print_curr_tests()

    @locked
    def on_test_end(self, test_res: TestResult) -> None:
        if not self.display.tests:
            return
        test = test_res.test
        msg = short_str(test.name, 40)
        msg = colorize_str(f"{msg:<45}", XColors.Bold)

        status_text = str(TestStatus(test_res.status.primary))
        status_suffix = ""
        if test_res.status.secondary != TestSecondaryStatus.Undefined:
            status_suffix = str(test_res.status)

        stts_str = colorize_str(status_text, _status_color(test_res.status.primary))
        msg += f"[{stts_str}]"

        if self.display.test_timing:
            if self.display.full_timing:
                msg += f" ({test_res.duration_str})"
            else:
                msg += f" ({test_res.main_res.duration_str})"

        if status_suffix:
            msg += f" {short_str(status_suffix, 30)}"

        if self.display.result_details:
            details = test_res.error_summary()
            if details:
                #  Escape special characters (e.g. Saure brackets) so rich won't get confused
                details = rich_escape(details)
                msg += f"\n{details}\n"
        self.curr_tests.remove(test.name)
        pr_info(msg)

    def on_iteration_start(self) -> None:
        if not self.display.tests:
            return
        if self.display.header:
            pr_info()
        if self.iteration_index > 0:
            pr_info()
        pr_info(self._iter_header(self.iteration_index))

    def _summarize_result_names(self, results: StatusTestsDict, show_names: bool, duration: float
                                ) -> None:
        stss = sorted(results.keys(), key=lambda x: x.primary.value)
        if not stss:
            pr_warn("No tests were run")
        else:
            for s in stss:
                names = results[s]
                msg = colorize_str(str(s), _status_color(s.primary))
                if show_names:
                    msg += f" ({len(names)}): " + ", ".join(names)
                else:
                    msg += f": {len(names)}"
                pr_info(msg)
        pr_info(f"Duration: {duration:.3f}s\n")

    def _iter_header(self, iter_i: int) -> str:
        assert self.run_res is not None
        return colorize_str(f"Iteration #{iter_i}/{self.iterations - 1}", _ITERATION_COLOR)

    def on_run_end(self) -> None:
        assert self.run_res is not None
        self.live.update("")
        if not self.display.summary:
            return
        show_iteration_summary = self.display.iteration_summary and self.iterations > 1

        pr_info()
        if self.display.tests:
            pr_info()

        summary_title = "Iterations Summary" if show_iteration_summary else "Summary"
        pr_info(underline(colorize_str(f"{summary_title}:", color=XColors.Bold),
                          underline_char='='))

        #  Collecting summary of results
        total_summary: StatusTestsDict = {}
        for iter_i, iter_res in enumerate(self.run_res.iter_results):
            iter_summary: StatusTestsDict = {}
            stss = sorted(iter_res.status_results_summary.keys(), key=lambda x: x.primary.value)
            for s in stss:
                test_names = iter_res.status_results_summary[s]
                if s not in iter_summary:
                    iter_summary[s] = list()
                iter_summary[s].extend(test_names)
                if s not in total_summary:
                    total_summary[s] = list()
                total_summary[s].extend(test_names)

        if show_iteration_summary:
            for iter_i, iter_res in enumerate(self.run_res.iter_results):
                header = self._iter_header(iter_i)
                header = underline(header, '-')
                pr_info(header)
                self._summarize_result_names(iter_res.status_results_summary,
                                             self.display.detailed_summary, iter_res.duration)
            pr_info()
            pr_info(underline(colorize_str("Accumulated summary:", color=XColors.Bold),
                              underline_char='-'))

        pr_info(f"Total iterations: {self.iterations}")
        pr_info(f"Threads used per iteration: {self.threads}")
        detailed = self.display.detailed_summary and not show_iteration_summary
        self._summarize_result_names(total_summary, detailed, self.run_res.duration)
