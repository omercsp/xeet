from typing import TYPE_CHECKING, Callable
from threading import Lock

if TYPE_CHECKING:
    from .result import RunResult, IterationResult, MtrxResult
    from . import RuntimeInfo
    from .test import Test
    from .matrix import Matrix, MatrixPermutation
from dataclasses import dataclass, field


@dataclass
class EventReporter:
    rti: "RuntimeInfo" = None  # type: ignore
    run_res: "RunResult | None" = None
    iter_res: "IterationResult | None" = None
    tests: list["Test"] = field(default_factory=list)
    threads: int = 1
    mtrx: "Matrix" = None  # type: ignore
    mtrx_prmttn: "MatrixPermutation" = None  # type: ignore
    mtrx_res: "MtrxResult" = None  # type: ignore

    @property
    def iterations(self) -> int:
        if self.run_res is None:
            return -1
        return self.run_res.iterations

    @property
    def iteration_index(self) -> int:
        if self.iter_res is None:
            return -1
        return self.iter_res.iter_n

    @property
    def mtrx_count(self) -> int:
        if self.run_res is None:
            return -1
        return self.run_res.mtrx_count

    @property
    def mtrx_prmttn_index(self) -> int:
        if self.mtrx_prmttn is None:
            return -1
        return self.mtrx_res.mpi

    # Global events
    def on_init(self) -> None:
        ...

    def on_run_start(self) -> None:
        ...

    def on_run_end(self) -> None:
        ...

    def on_iteration_start(self) -> None:
        ...

    def on_iteration_end(self) -> None:
        ...

    def on_matrix_start(self) -> None:
        pass

    def on_matrix_end(self) -> None:
        pass

    # Test events
    def on_test_start(self, **_) -> None:
        ...

    def on_test_end(self, **_) -> None:
        ...

    def on_phase_start(self, **_) -> None:
        ...

    def on_phase_end(self, **_) -> None:
        ...

    # Step events
    def on_step_start(self, **_) -> None:
        ...

    def on_step_end(self, **_) -> None:
        ...

    # General event message
    def on_run_message(self, *_, **__) -> None:
        ...

    def on_test_message(self, *_, **__) -> None:
        ...

    def on_step_message(self, *_, **__) -> None:
        ...


class EventNotifier:
    def __init__(self):
        self._reporters: list[EventReporter] = []
        self._lock: Lock = Lock()
        #  Find all methods that begin with "on_test" or "on_phase" or "on_step"
        for m in dir(self):
            if m.startswith("on_test") or m.startswith("on_phase") or m.startswith("on_step") or \
                    m == "on_run_message":
                setattr(self, m, self._test_event(m))

    def _test_event(self, method_name: str) -> Callable[[EventReporter,], None]:
        def _handler(*args, **kwargs) -> None:
            with self._lock:
                for r in self._reporters:
                    if not hasattr(r, method_name):
                        continue
                    method = getattr(r, method_name)
                    method(*args, **kwargs)
        return _handler

    def add_reporter(self, reporter: EventReporter) -> None:
        self._reporters.append(reporter)

    def on_init(self) -> None:
        for r in self._reporters:
            r.on_init()

    #  Global events
    def on_run_start(self, run_res: "RunResult", tests: list["Test"], mtrx: "Matrix", threads: int
                     ) -> None:
        for r in self._reporters:
            r.run_res = run_res
            r.tests = tests
            r.threads = threads
            r.mtrx = mtrx
            r.on_run_start()

    def on_run_end(self) -> None:
        for r in self._reporters:
            r.on_run_end()
            r.run_res = None

    def on_iteration_start(self, iter_res: "IterationResult") -> None:
        for r in self._reporters:
            r.iter_res = iter_res
            r.on_iteration_start()

    def on_iteration_end(self) -> None:
        for r in self._reporters:
            r.on_iteration_end()
            r.iter_res = None

    def on_matrix_start(self, mtrx_prmttn: "MatrixPermutation", mtrx_res: "MtrxResult") -> None:
        for r in self._reporters:
            r.mtrx_res = mtrx_res
            r.mtrx_prmttn = mtrx_prmttn
            r.on_matrix_start()

    def on_matrix_end(self) -> None:
        for r in self._reporters:
            r.on_matrix_end()
            r.mtrx_prmttn = None  # type: ignore
            r.mtrx_res = None  # type: ignore

    # Test events
    def on_test_start(self, **_) -> None:
        ...

    def on_test_end(self, **_) -> None:
        ...

    def on_phase_start(self, **_) -> None:
        ...

    def on_phase_end(self, **_) -> None:
        ...

    # Step events
    def on_step_init(self, **_) -> None:
        ...

    def on_step_start(self, **_) -> None:
        ...

    def on_step_end(self, **_) -> None:
        ...

    # General event message
    def on_run_message(self, *_, **__) -> None:
        ...

    def on_test_message(self, *_, **__) -> None:
        ...

    def on_step_message(self, *_, **__) -> None:
        ...
