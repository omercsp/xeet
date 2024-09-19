from typing import Any


#  Base class for run reporters (CLI, REST, etc.)
class RunReporter:
    def __init__(self, iterations: int) -> None:
        super().__init__()
        self.run_info: Any = None
        self.iter_info: Any = None
        self.iteration: int = 0
        self.iterations: int = iterations
        self.xtest: Any = None
        self.xtest_result: Any = None
        self.xstep: Any = None
        self.xstep_index: int = 0
        self.steps_count: int = 0
        self.xstep_result: Any = None
        self.phase_name: str = ""
        self.tests: list = []  # Not fully annotated to avoid circular import

    def on_run_start(self, run_info, tests: list) -> None:
        self.run_info = run_info
        self.tests = tests
        self.client_on_run_start()

    def client_on_run_start(self) -> None:
        pass

    def on_run_end(self) -> None:
        self.client_on_run_end()

    def client_on_run_end(self) -> None:
        pass

    def on_iteration_start(self, iter_info, iter_index) -> None:
        self.iter_info = iter_info
        self.iteration = iter_index
        self.client_on_iteration_start()

    def client_on_iteration_start(self) -> None:
        pass

    def on_iteration_end(self) -> None:
        self.client_on_iteration_end()
        self.iter_info = None
        self.iteration = -1

    def client_on_iteration_end(self) -> None:
        pass

    def on_test_enter(self, test) -> None:
        self.xtest = test
        self.client_on_test_enter()

    def on_test_setup_start(self, test) -> None:
        self.xtest = test
        self.client_on_test_setup_start()

    def client_on_test_setup_start(self) -> None:
        pass

    def on_test_setup_end(self) -> None:
        self.client_on_test_setup_end()

    def client_on_test_setup_end(self) -> None:
        pass

    def on_step_setup_start(self, step, step_index: int) -> None:
        self.xstep = step
        self.xstep_index = step_index
        self.client_on_step_setup_start()

    def client_on_step_setup_start(self) -> None:
        pass

    def on_step_setup_end(self) -> None:
        self.client_on_step_setup_end()
        self.xstep = None
        self.xstep_index = -1

    def client_on_step_setup_end(self) -> None:
        pass

    def client_on_test_enter(self) -> None:
        pass

    def on_test_end(self, res) -> None:
        self.xtest_result = res
        self.client_on_test_end()
        self.xtest = None
        self.xtest_result = None

    def client_on_test_end(self) -> None:
        pass

    def on_phase_start(self, phase_name: str, steps_count: int) -> None:
        self.phase_name = phase_name
        self.steps_count = steps_count
        self.client_on_phase_start()

    def client_on_phase_start(self) -> None:
        pass

    def on_phase_end(self) -> None:
        self.client_on_phase_end()
        self.phase_name = ""
        self.steps_count = 0

    def client_on_phase_end(self) -> None:
        pass

    def on_step_start(self, step, step_index: int) -> None:
        self.xstep = step
        self.xstep_index = step_index
        self.client_on_step_start()

    def client_on_step_start(self) -> None:
        pass

    def on_step_end(self, res) -> None:
        self.xstep_result = res
        self.client_on_step_end()
        self.xstep = None
        self.xstep_index = -1
        self.xstep_result = None

    def client_on_step_end(self) -> None:
        pass
