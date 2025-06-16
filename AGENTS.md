# xeet — Agent Context

xeet is a YAML/JSON-driven **test orchestrator**: it reads a declarative
config describing tests, builds a tree of tests -> phases -> steps,
executes them, and reports results. It is not a test framework for one
language — it orchestrates arbitrary external commands (and its own step
types) as "tests".

Packaged as `xeet` (PyPI), entry point `xeet.__main__:xrun`
(`pyproject.toml`). Python >=3.10. Key deps: `pydantic>=2.9` (all
models/validation/schema generation), `pyyaml`, `jsonpath-ng` (config
references), `rich` (console output), `argcomplete`.

CLI surface (`src/xeet/args.py`): `run`, `list`, `groups`, `info`,
`dump {test,schema,config}`.

## Architecture

Layers, dependencies flow one way:

```
args.py -> cli.py -> core/api.py -> core/driver.py -> core/test.py -> core/step.py
(argparse)  (actions)  (thin facade)   (_XeetDriver)     (Test/Phase)    (Step ABC)
                                             |                                ^
   pr.py / log.py (output + logging)        |                          steps/{exec,dummy}
   reporters/ (EventReporter impls) <--------+---- core/events.py (EventNotifier)
   common.py (XeetVars, validators, filters)
```

| Module | Role |
|---|---|
| `core/conf.py` | YAML/JSON load, `XeetConfModel`, recursive `include` merge with loop detection |
| `core/driver.py` | `_XeetDriver` — builds all `Test`s, resolves test inheritance, filters by criteria, drives iterations (distributing tests to `_TestRunner` worker threads via `_TestsPool`, synchronizing on shared resource pools). `xeet_driver()` is `@cache`d on `XeetSettings.__hash__` (= config file path) — clear/bypass the cache if a config is rewritten and re-driven within the same process |
| `core/test.py` | `TestModel` (pydantic) + `Test` runtime + `Phase`; phase status logic |
| `core/step.py` | `StepModel` + `Step` base class — the step plugin contract |
| `core/result.py` | Result tree: `RunResult -> IterationResult -> MtrxResult -> TestResult -> PhaseResult -> StepResult`, all `MeasuredResult` (timed via the `@time_result` decorator) |
| `core/events.py` | Observer pattern — `EventNotifier` fans out to `EventReporter`s |
| `core/__init__.py` | `RuntimeInfo` — holds cwd/dirs/xvars/notifier/iteration state; `TestsCriteria` (test selection filter) |
| `core/resource.py` | `ResourceModel`, `Resource`, `ResourcePool` — in-memory resource allocation pool (FIFO or by name) |
| `core/matrix.py` | `Matrix`, `MatrixModel`, `MatrixPermutation` — cartesian product permutation generator |
| `steps/exec_step.py`, `steps/dummy_step.py` | The two built-in step types |
| `reporters/` | `ConsolePrinter` (normal run output), `ConsoleDebugPrinter` (`--debug`) |

### Execution flow

`xrun` -> `run_tests` -> `xeet_driver(settings)` -> for each iteration ->
for each test -> obtain resources (defer if busy) -> `Test.run()` ->
`setup()` -> three phases (`pre`/`main`/`post`) -> per step `Step.run()` ->
release resources.

Phase semantics (`core/test.py`, `Test._exec_phase`):
- `pre` (output dir `pre0`, stop-on-error) — failure => test
  `NotRun/PreTestErr`
- `main` (output dir `stp0`, stop-on-error) — failure => `Failed`;
  incomplete => `NotRun/TestErr`; honors `expected_failure`
- `post` (output dir `pst0`, **not** stop-on-error) — failure only sets
  `post_run_status` plus a warning, it does not fail the test

Exit code contract (`cli.py:run_tests`): `0` ok, `+1` if any test failed,
`+2` if any test didn't run => `3` means both happened.

## Domain model — two inheritance systems (don't conflate them)

**Test inheritance** — `TestModel.base` names another *test*. Resolved in
`_XeetDriver._test_model` with loop detection. `TestModel.set_parent()`
stores a parent link; values are computed lazily via `variables()` and
`pre_run_steps()/run_steps()/post_run_steps()`, merged per
`*_inheritance: prepend|append|replace` (default `replace`).
`short_desc`/`long_desc`/`skip`/`expected_failure` are deliberately **not**
inherited.

**Step inheritance** — `StepModel.base` is a **JSONPath into the config
document** (e.g. `settings.common_steps.hello`, `tests[0].run[2]`),
resolved via `RuntimeInfo.config_ref()` -> `json_value()`.
`StepModel.set_parent()` eagerly copies unset attributes from the parent. A
step's `type` must match its base's type if both specify one.

## Variable system (`common.py:XeetVars`)

Two syntaxes, resolved through a scoped parent chain (`RuntimeInfo.xvars`
-> `Test.xvars` -> per-step `XeetVars`):
- `{name}` — string interpolation, recursive, `\{` escapes a literal
  brace, `{$ENV}` reads an OS environment variable
- `$ref://name.path` — whole-value reference (preserves dict/list types,
  unlike `{}` which always stringifies)

System variables (prefix `XEET_`; user variables using this prefix are
rejected at validation time): `XEET_CWD`, `XEET_ROOT`, `XEET_OUT_DIR`,
`XEET_EXPECTED_DIR`, `XEET_TEST_NAME`, `XEET_TEST_BASE_NAME`,
`XEET_TEST_OUT_DIR`, `XEET_STEP_OUT_DIR`, `XEET_STEP_INDEX`,
`XEET_ITERATIONS`, `XEET_DEBUG`, `XEET_PLATFORM`, `XEET_MATRIX_INDEX`,
`XEET_MATRIX_COUNT`, `XEET_MATRIX_PERMUTATION`.

## Extension points

- **New step type**: subclass `Step` + `StepModel` (`core/step.py`);
  override `model_class()`, `result_class()`, `setup()`, `_run()`, and the
  details-reporting hooks (`_details_keys`, `_field_details_order`,
  `_detail_value`, `_printable_field_name`); register the pair in
  `steps/__init__.py:_XSTEP_CLASSES`.
- **New reporter**: subclass `EventReporter` (`core/events.py`); append an
  instance to `XeetSettings.reporters` before driving a run.
- Only `exec` and `dummy` steps exist today. `dummy` has no side effects
  and exists purely so core logic (inheritance, phases, statuses) can be
  unit-tested without spawning subprocesses.

## Conventions

- pycodestyle, `max-line-length = 100`. There is no repo-local config file
  for this — it comes from `~/.config/pycodestyle`.
- Type hints throughout; guard-clause / early-return style; prevailing
  comment style is `#`, not docstrings.
- Commit subjects: `<topic>: <lower-case description>` — topics seen so
  far include `xeet`, `core`, `unit`, `ut`, `test`, `cli`, `common`, `build`.

## Repository history note

This `devel` branch is a ground-up **rehaul** — its root commit
(`xeet: initial commit (rehaul)`) starts the architecture described above
from scratch, with no shared history with `master` (`git merge-base` finds
no common ancestor). The `master` branch contains features not
yet fully ported to this architecture: test randomization.
See `TODO.txt` for the running list of what's still missing on `devel`
(test randomization, etc.) — treat it as the feature backlog.

## Testing

### Unit tests (`src/ut/`)

pytest-based, run via `cd src/ut && ./utxeet` (auto-activates `.venv`, runs
with `pytest-xdist` at `nproc/2` workers; pass args through, e.g.
`./utxeet -x test_core.py -k test_step_details`).

Infrastructure lives in `src/ut/__init__.py` and `conftest.py`:
- `conftest.py`'s `xeet_dir_setup` (session-scoped, autouse) creates one
  shared temp dir per process; the `xut` fixture hands back a
  process-cached `XeetUnittest("main.yaml")`, reset before each test.
- `ConfigTestWrapper` builds an in-memory config via `add_test()`,
  `add_var()`, `add_setting()`, `add_resource()`, `add_matrix()`, `add_include()` (each accepts
  `reset=`, `save=`, `show=` kwargs) and writes it to disk with `.save()`.
- `XeetUnittest` (extends `ConfigTestWrapper`) drives it: `run_test(name)`,
  `run_tests(**TestsCriteria kwargs)`, `get_test(name)`, `driver()`. Any
  time the config is rewritten, `.save()`/`.reset()` call
  `xeet_driver.cache_clear()` — required because `xeet_driver()` is
  `@cache`d on the config file path (see Architecture table above).
- `gen_test_result()` / `assert_test_results_equal()` build and compare
  expected `TestResult` trees. Adding a new step type requires a sibling
  `ut_<type>_defs.py` with `gen_*_desc()`/`gen_*_result()` and a call to
  `register_res_comparison(YourStepResult, fn)` — otherwise result
  comparison raises `ValueError`.
- `scripts/testing/*.py` (`echo.py`, `rc.py`, `pwd.py`, `sleep.py`,
  `showenv.py`, `output.py`, `output_stream.py`) are small dependency-free
  Python scripts used as deterministic, cross-platform exec-step targets
  by `ut_exec_defs.py` (and later by the E2E testbed).

### End-to-end / self-hosting tests (`tests/`)

xeet testing itself: an **outer** xeet run drives `tests/xeet.yaml`, whose
steps invoke an **inner** xeet against `tests/testbed/*.yaml`, then diff
the (filtered) captured output against golden files.

- Run via `cd tests && ./runtests [-z NNN]` — it **refuses to run inside a
  virtualenv**: the outer xeet must be a stable system install (`xeet` on
  `PATH`), while the inner xeet is the dev tree, reached through the
  repo-root `./xeet` launcher, which activates `.venv` (or
  `$XEET_PKG_VENV_PATH`, set by `tests/run_pkg_tests` when smoke-testing a
  PyPI build instead of the working tree).
- `tests/testbed/xeet_base.yaml` — shared variables + a `settings.
  common_steps.*` step library; `inheritance.yaml` — abstract base tests
  for exercising `*_inheritance` modes; `xeet.yaml` — the ~31 inner tests
  covering pass/fail/skip/phases/inheritance; `xeet_debug.yaml` — tests for
  `--debug` live output tailing.
- Golden files live in `tests/xeet.expected/` (tracked); actual runs land
  in `tests/xeet.out/` (gitignored). `output_filters` on the outer steps
  scrub `{XEET_ROOT}` -> `__XEET_ROOT__` and durations -> `X.XXXs` for
  hermetic, machine-independent comparison; the filtered actual output is
  a side effect written as `<file>.filtered` next to the raw output.
  Baseline workflow: `./diff_test_output.sh NNN`, `./update_test_output.sh
  NNN` (accept), `./create_new_test.sh NNN` (bootstrap); all fuzzy-match a
  numeric prefix to a full test directory name.
- Each outer test also asserts the inner xeet's **exit code** via
  `allowed_rc`, tying back to the `0/1/2/3` contract above.

## Verification checklist before finishing a change

1. `pycodestyle --max-line-length=100 <changed files>` — must be clean.
2. `cd src/ut && ./utxeet` — unit suite must pass.
3. `cd tests && ./runtests` — E2E suite must pass (run outside a venv).
