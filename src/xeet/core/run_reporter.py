#  Base class for run reporters (CLI, REST, etc.)
class RunReporter:
    def __init__(self) -> None:
        self.run_res = None
        self.iter_res = None
        self.iteration = 0
        self.iterations = -1

    # Global events
    def on_run_start(self, tests: list) -> None:
        pass

    def on_run_end(self) -> None:
        pass

    def on_iteration_start(self) -> None:
        pass

    def on_iteration_end(self) -> None:
        pass

    # Test events
    def on_test_start(self, test) -> None:
        pass

    def on_test_end(self, test, test_res) -> None:
        pass

    def on_test_setup_start(self, test) -> None:
        pass

    def on_test_setup_end(self, test) -> None:
        pass

    def on_phase_start(self, test, phase_name: str, steps_count: int) -> None:
        pass

    def on_phase_end(self, test, phase_name: str, steps_count: int) -> None:
        pass

    # Step events
    def on_step_setup_start(self, test, phase_name: str, step, step_index: int) -> None:
        pass

    def on_step_setup_end(self, test, phase_name: str, step, step_index: int) -> None:
        pass

    def on_step_start(self, test, phase_name: str, step, step_index: int) -> None:
        pass

    def on_step_end(self, test, phase_name: str, step, step_index: int, step_res) -> None:
        pass


class RunNotifier:
    def __init__(self,  reporters: list[RunReporter]) -> None:
        super().__init__()
        self.reporters: list[RunReporter] = reporters

    #  Global events
    def on_run_start(self, run_res, tests: list) -> None:
        for r in self.reporters:
            r.run_res = run_res
            r.on_run_start(tests)

    def on_run_end(self) -> None:
        for r in self.reporters:
            r.on_run_end()
            r.run_res = None

    def on_iteration_start(self, iter_res, iteration: int) -> None:
        for r in self.reporters:
            r.iter_res = iter_res
            r.iteration = iteration
            r.on_iteration_start()

    def on_iteration_end(self) -> None:
        for r in self.reporters:
            r.on_iteration_end()
            r.iter_res = None
            r.iteration = -1

    #  Test events
    def on_test_start(self, test) -> None:
        for r in self.reporters:
            r.on_test_start(test)

    def on_test_end(self, test, test_res) -> None:
        for r in self.reporters:
            r.on_test_end(test, test_res)

    def on_test_setup_start(self, test) -> None:
        for r in self.reporters:
            r.on_test_setup_start(test)

    def on_test_setup_end(self, test) -> None:
        for r in self.reporters:
            r.on_test_setup_end(test)

    def on_phase_start(self, test, phase_name: str, steps_count: int) -> None:
        for r in self.reporters:
            r.on_phase_start(test, phase_name, steps_count)

    def on_phase_end(self, test, phase_name, steps_count: int) -> None:
        for r in self.reporters:
            r.on_phase_end(test, phase_name, steps_count)

    # Step events
    def on_step_setup_start(self, test, phase_name: str, step, step_index: int) -> None:
        for r in self.reporters:
            r.on_step_setup_start(test, phase_name, step, step_index)

    def on_step_setup_end(self, test, phase_name: str, step, step_index: int) -> None:
        for r in self.reporters:
            r.on_step_setup_end(test, phase_name, step, step_index)

    def on_step_start(self, test, phase_name: str, step, step_index: int) -> None:
        for r in self.reporters:
            r.on_step_start(test, phase_name, step, step_index)

    def on_step_end(self, test, phase_name: str, step, step_index: int, step_res) -> None:
        for r in self.reporters:
            r.on_step_end(test, phase_name, step, step_index, step_res)
