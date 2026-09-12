from enum import Enum
from dataclasses import dataclass


class ConsoleReporterVerbosity(str, Enum):
    Default = "default"
    Quiet = "quiet"
    Concise = "concise"
    Verbose = "verbose"


@dataclass
class BaseConsoleReporterOpts:
    _verbosity: ConsoleReporterVerbosity = ConsoleReporterVerbosity.Default

    def set_verbose(self):
        self._verbosity = ConsoleReporterVerbosity.Verbose

    def set_concise(self):
        self._verbosity = ConsoleReporterVerbosity.Concise

    def set_quiet(self):
        self._verbosity = ConsoleReporterVerbosity.Quiet
