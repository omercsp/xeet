from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .xres import RunResult, IterationResult, TestResult, XStepResult
    from .xtest import Xtest
    from .xstep import XStep
from dataclasses import dataclass
from threading import Lock


#  Base class for run reporters (CLI, REST, etc.)
@dataclass
class RunReporter:
    run_res: "RunResult" = None  # type: ignore
    iter_res: "IterationResult" = None  # type: ignore
    iteration = 0

    @property
    def iterations(self) -> int:
        return self.run_res.iterations

    # Global events
    def on_run_start(self, **_) -> None:
        pass

    def on_run_end(self) -> None:
        pass

    def on_iteration_start(self) -> None:
        pass

    def on_iteration_end(self) -> None:
        pass

    # Test events
    def on_test_start(self, **_) -> None:
        pass

    def on_test_end(self, **_) -> None:
        pass

    def on_phase_start(self, **_) -> None:
        pass

    def on_phase_end(self, **_) -> None:
        pass

    # Step events
    def on_step_start(self, **_) -> None:
        pass

    def on_step_end(self, **_) -> None:
        pass


class RunNotifier:
    def __init__(self,  reporters: list[RunReporter]) -> None:
        super().__init__()
        self.reporters: list[RunReporter] = reporters
        self._lock = Lock()

    #  Global events
    def on_run_start(self, run_res: "RunResult", tests: list) -> None:
        for r in self.reporters:
            r.run_res = run_res
            r.on_run_start(tests=tests)

    def on_run_end(self) -> None:
        for r in self.reporters:
            r.on_run_end()
            r.run_res = None  # type: ignore

    def on_iteration_start(self, iter_res: "IterationResult", iteration: int) -> None:
        for r in self.reporters:
            r.iter_res = iter_res
            r.iteration = iteration
            r.on_iteration_start()

    def on_iteration_end(self) -> None:
        for r in self.reporters:
            r.on_iteration_end()
            r.iter_res = None  # type: ignore
            r.iteration = -1

    #  Test events
    def on_test_start(self, test: "Xtest") -> None:
        with self._lock:
            for r in self.reporters:
                r.on_test_start(test=test)

    def on_test_end(self, test: "Xtest", test_res: "TestResult") -> None:
        with self._lock:
            for r in self.reporters:
                r.on_test_end(test=test, test_res=test_res)

    def on_phase_start(self, test: "Xtest", phase_name: str, steps_count: int) -> None:
        with self._lock:
            for r in self.reporters:
                r.on_phase_start(test=test, phase_name=phase_name, steps_count=steps_count)

    def on_phase_end(self, test: "Xtest", phase_name: str, steps_count: int) -> None:
        with self._lock:
            for r in self.reporters:
                r.on_phase_end(test=test, phase_name=phase_name, steps_count=steps_count)

    # Step events
    def on_step_start(self, test: "Xtest", phase_name: str, step: "XStep", step_index: int) -> None:
        with self._lock:
            for r in self.reporters:
                r.on_step_start(test=test, phase_name=phase_name, step=step, step_index=step_index)

    def on_step_end(self, test: "Xtest", phase_name: str, step: "XStep", step_index: int,
                    step_res: "XStepResult") -> None:
        with self._lock:
            for r in self.reporters:
                r.on_step_end(test=test, phase_name=phase_name, step=step, step_index=step_index,
                              step_res=step_res)
