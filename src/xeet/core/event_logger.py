from .result import TestResult
from .events import EventReporter
from xeet.pr import *
from xeet.log import log_info, log_warn, log_general, log_depth
from xeet.core.test import Test, Phase
from xeet.core.step import Step
from xeet.core.result import PhaseResult
from dataclasses import dataclass
from functools import cache


@dataclass
class EventLogger(EventReporter):

    @cache
    def _step_prefix(self, step: Step) -> str:
        return f"{step.phase.name}{step.step_index}.{self._test_prefix(step.test)}"

    @cache
    def _test_prefix(self, test: Test) -> str:
        #  Messages issued before the run starts will occur before run result and iteration result
        #  are set
        if self.run_res is None or self.iter_res is None or self.run_res.iterations == 1:
            return test.name
        return f"{test.name}@i{self.iter_res.iter_n}"

    def __hash__(self):
        return hash(id(self))

    @log_depth(3)
    def _log_info(self, *args, **kwargs) -> None:
        log_info(*args, **kwargs)

    @log_depth(3)
    def _log_warn(self, *args, **kwargs) -> None:
        log_warn(*args, **kwargs)

    @log_depth(3)
    def _log_bad_args(self, **kwargs) -> None:
        for k, v in kwargs.items():
            if v is None:
                self._log_warn(f"Bad argument: {k} is None")

    # Global events
    def on_init(self) -> None:
        self._log_info(f"Main Xeet configuration file: {self.rti.xeet_file_path}")
        self._log_info(f"Root directory: {self.rti.root_dir}")
        self._log_info(f"Current working directory: {self.rti.cwd}")
        if self.run_res:
            log_info(str(self.run_res.criteria))

    def on_run_start(self, **_) -> None:
        self._log_info("Starting run", pr_suffix="------------\n")
        self._log_info(f"Expected output directory: {self.rti.expected_output_dir}")
        self._log_info("Tests run list: {}".format(", ".join([x.name for x in self.tests])))

    def on_iteration_start(self) -> None:
        if self.iter_res is None or self.run_res is None:
            self._log_bad_args(iter_res=self.iter_res, run_res=self.run_res)
            return
        if self.run_res.iterations == 1:
            return
        self._log_info(f">>> Iteration {self.iter_res.iter_n}/{self.run_res.iterations - 1}")

    def on_iteration_end(self) -> None:
        if self.iter_res is None or self.run_res is None:
            self._log_bad_args(iter_res=self.iter_res, run_res=self.run_res)
            return
        if self.run_res.iterations > 1:
            self._log_info(f"Finished iteration #{self.iter_res.iter_n}/{self.iterations - 1}")
        else:
            self._log_info("Finished run")

        for status, test_names in self.iter_res.status_results_summary.items():
            if not test_names:
                continue
            test_list_str = ", ".join(test_names)
            self._log_info(f"{status}: {test_list_str}")
        self._step_prefix.cache_clear()
        self._test_prefix.cache_clear()

    # Test events
    def on_test_start(self, test: Test | None = None, **_) -> None:
        assert test is not None
        self._log_info(f"Running test '{test.name}'")

    def on_test_end(self, test: Test | None = None, test_res: TestResult | None = None, **_
                    ) -> None:
        if test_res is None or test is None:
            self._log_bad_args(test_res=test_res, test=test)
            return
        self._log_info(f"Test '{test.name}' completed - {test_res.status}")

    def on_phase_start(self, phase: Phase | None = None, **_) -> None:
        if phase is None:
            self._log_bad_args(phase=phase)
            return

        self._log_info(f"{phase.test.name}: running {phase.name} phase ({len(phase.steps)})")

    def on_phase_end(self, phase: Phase | None = None, phase_res: PhaseResult | None = None, **_
                     ) -> None:
        if phase is None or phase_res is None:
            self._log_bad_args(phase=phase, phase_res=phase_res)
            return

        test_name = phase.test.name
        if phase_res.completed and not phase_res.failed:
            self._log_info(f"{test_name}: phase {phase.name} completed")
            return

        err = phase_res.error_summary()
        if not phase_res.completed:
            self._log_info(f"{test_name}: {phase.name} didn't complete - {err}")
        else:
            self._log_info(f"{test_name}: {phase.name} failed - {err}")

    # General event message
    @log_depth(3)
    def on_test_message(self, msg: str, *args, **kwargs) -> None:
        if kwargs.pop("dbg_pr", False):
            return
        test: Test | None = kwargs.pop("test")
        prefix = self._test_prefix(test)
        if test is None:
            log_warn("Test is None")
            return
        log_general(f"{prefix}: {msg}", *args, **kwargs)

    @log_depth(3)
    def on_step_message(self, msg: str, *args, **kwargs) -> None:
        if kwargs.pop("dbg_pr", False):
            return
        step: Step | None = kwargs.pop("step")
        prefix = self._step_prefix(step)
        if step is None:
            log_warn("Step is None")
            return
        log_general(f"{prefix}: {msg}", *args, **kwargs)

    @log_depth(3)
    def on_run_message(self, msg: str, *args, **kwargs) -> None:
        if kwargs.pop("dbg_pr", False):
            return
        log_general(msg, *args, **kwargs)
