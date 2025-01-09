from .result import TestResult
from .events import EventReporter
from xeet.pr import *
from xeet.log import log_info, log_warn, log_general, log_depth
from xeet.core.test import Test, Phase
from xeet.core.step import Step
from xeet.core.result import PhaseResult, StepResult
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

    # Global events
    def on_init(self) -> None:
        self._log_info(f"main xeet file: {self.rti.xeet_file_path}")
        self._log_info(f"root directory: {self.rti.root_dir}")
        self._log_info(f"current working directory: {self.rti.cwd}")
        if self.run_res:
            log_info(str(self.run_res.criteria))

    def on_run_start(self, **_) -> None:
        self._log_info("starting run", pr_suffix="------------\n")
        self._log_info(f"expected output directory: {self.rti.expected_output_dir}")
        self._log_info("tests run list: {}".format(", ".join([x.name for x in self.tests])))
        self._log_info(f"threads: {self.threads}")

    def on_run_end(self) -> None:
        assert self.run_res is not None
        self._log_info(f"finished run ({self.run_res.duration_str})")

    def on_iteration_start(self) -> None:
        assert self.iter_res is not None
        assert self.run_res is not None
        if self.run_res.iterations == 1:
            return
        self._log_info(f">>> iteration {self.iter_res.iter_n}/{self.run_res.iterations - 1}")

    def on_iteration_end(self) -> None:
        assert self.iter_res is not None
        assert self.run_res is not None
        if self.run_res.iterations > 1:
            self._log_info(f"finished iteration #{self.iter_res.iter_n}/{self.iterations - 1}")

        for status, test_names in self.iter_res.status_results_summary.items():
            if not test_names:
                continue
            test_list_str = ", ".join(test_names)
            status = str(status).lower()
            self._log_info(f"{status}: {test_list_str}")
        self._step_prefix.cache_clear()
        self._test_prefix.cache_clear()

    # Test events
    def on_test_start(self, test: Test | None = None, runner_id: int = 0, **_) -> None:
        assert test is not None
        self._log_info(f"running test '{test.name}' by runner {runner_id}")

    def on_test_end(self, test_res: TestResult) -> None:
        test = test_res.test
        self._log_info(
            f"test '{test.name}' completed - {test_res.status} ({test_res.duration_str})")

    def on_phase_start(self, phase: Phase) -> None:
        self._log_info(f"{phase.test.name}: running {phase.name} phase ({len(phase.steps)})")

    def on_phase_end(self, phase_res: PhaseResult) -> None:
        phase = phase_res.phase
        test_name = phase.test.name
        if phase_res.completed and not phase_res.failed:
            msg = (f"{test_name}: phase {phase.name} completed")
        else:
            err = phase_res.error_summary()
            if not phase_res.completed:
                msg = f"{test_name}: {phase.name} didn't complete - {err}"
            else:
                msg = f"{test_name}: {phase.name} failed - {err}"
        msg += f" ({phase_res.duration_str})"
        self._log_info(msg)

    def on_step_end(self, step_res: StepResult) -> None:
        step = step_res.step
        prefix = self._step_prefix(step)
        msg = f"{prefix}: "
        if not step_res.completed:
            msg += "incomplete"
        elif step_res.failed:
            msg += "failed"
        else:
            msg += "passed"
        msg += f" ({step_res.duration_str})"
        self._log_info(msg)

    # General event message
    @log_depth(3)
    def on_test_message(self, test: Test, msg: str, *args, **kwargs) -> None:
        if kwargs.pop("dbg_pr", False):
            return
        prefix = self._test_prefix(test)
        log_general(f"{prefix}: {msg}", *args, **kwargs)

    @log_depth(3)
    def on_step_message(self, step: Step, msg: str, *args, **kwargs) -> None:
        if kwargs.pop("dbg_pr", False):
            return
        prefix = self._step_prefix(step)
        log_general(f"{prefix}: {msg}", *args, **kwargs)

    @log_depth(3)
    def on_run_message(self, msg: str, *args, **kwargs) -> None:
        if kwargs.pop("dbg_pr", False):
            return
        log_general(msg, *args, **kwargs)
