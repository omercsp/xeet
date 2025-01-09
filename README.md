# xeet

> Declarative, language-agnostic test orchestrator driven by YAML and JSON.

**xeet** is an end-to-end testing framework and test runner. Instead of embedding test logic inside a specific programming language, xeet defines test suites declaratively in configuration files, orchestrating arbitrary commands, scripts, and processes across structured execution phases with automated verification.

---

## Key Features

- **Language-Agnostic**: Orchestrate CLI binaries, test scripts, APIs, or shell commands across any stack.
- **Declarative Configuration**: Define suites in YAML or JSON with support for modular `include` files.
- **Phased Test Execution**:
  - `pre_run` — Setup steps that stop on failure.
  - `run` — Main test execution with expected exit codes, timeouts, and output verification.
  - `post_run` — Cleanup and tear-down steps that execute even if main steps fail.
- **Dual Inheritance Model**:
  - **Test Inheritance**: Re-use and extend base test definitions (`prepend`, `append`, or `replace` steps).
  - **Step Inheritance**: Reference reusable step definitions via JSONPath (`settings.common_steps.*`).
- **Flexible Verification**: Match standard output and standard error against strings or expected files, with regex/string scrubbing filters for hermetic diffs.
- **Scoped Variable System**: Recursive string interpolation (`{var}`), environment variable access (`{$ENV_VAR}`), object references (`$ref://...`), and built-in runtime variables (`{XEET_ROOT}`, `{XEET_OUT_DIR}`, etc.).
- **Platform-Specific Testing**: Target specific OS environments (`posix`, `nt`), inherit platform constraints, and load platform-specific config files dynamically via `{XEET_PLATFORM}`.
- **Parallel Execution**: Execute tests concurrently across worker threads with `-j/--jobs` (defaults to auto-detecting core count).
- **Fine-Grained Filtering**: Select tests by exact name, fuzzy match, or tag groups with include/exclude rules.
- **Rich Terminal UI**: Live progress display with customizable output detail, timing breakdowns, and `--debug` live process tailing.

---

## Installation

Requires **Python >= 3.10**.

```bash
pip install xeet
```

Or install from source:

```bash
git clone https://github.com/omercsp/xeet.git
cd xeet
pip install .
```

---

## Quick Start

Create a configuration file named `xeet.yaml`:

```yaml
variables:
  greeting: "Hello, World!"

settings:
  xeet:
    default_step_type: exec

tests:
  - name: hello_world
    short_desc: Verify basic echo command
    groups: [smoke, sanity]
    run:
      - cmd: echo "{greeting}"
        expected_stdout: "Hello, World!\n"

  - name: check_system
    short_desc: Run a system check with environment variables
    groups: [sanity]
    pre_run:
      - cmd: mkdir -p "{XEET_TEST_OUT_DIR}/data"
    run:
      - cmd: python -c "import os; print(os.environ['APP_ENV'])"
        env:
          APP_ENV: "testing"
        expected_stdout: "testing\n"
    post_run:
      - cmd: rm -rf "{XEET_TEST_OUT_DIR}/data"
```

Run the suite:

```bash
xeet run
```

---

## Configuration Guide

A xeet configuration file (`xeet.yaml`, `xeet.yml`, or `xeet.json`) consists of four primary sections:

### 1. `include`
Modularize configurations by including other YAML/JSON files. Includes are merged recursively with loop detection:

```yaml
include:
  - shared_variables.yaml
  - step_library.yaml
```

### 2. `variables`
Define scoped variables for string interpolation (`{var_name}`) or object references (`$ref://var_name`):

```yaml
variables:
  api_host: "http://localhost:8080"
  timeout_sec: 5
  db_config:
    user: "admin"
    port: 5432
```

- **Environment variables**: Access system environment via `{$ENV_VAR_NAME}`.
- **Escaping**: Use `\{` to escape literal braces.
- **Built-in System Variables**:
  - `{XEET_CWD}` — Current working directory at launch.
  - `{XEET_ROOT}` — Directory containing the active configuration file.
  - `{XEET_OUT_DIR}` — Output directory root for test runs.
  - `{XEET_EXPECTED_DIR}` — Expected baselines directory root.
  - `{XEET_TEST_NAME}` — Name of the currently executing test.
  - `{XEET_TEST_OUT_DIR}` — Output directory dedicated to the current test.
  - `{XEET_STEP_OUT_DIR}` — Output directory for the current step.
  - `{XEET_STEP_INDEX}` — Zero-based index of the step within its phase.
  - `{XEET_ITERATIONS}` — Total iteration count (`-r` flag).
  - `{XEET_DEBUG}` — Set to `1` when `--debug` is active, otherwise `0`.
  - `{XEET_PLATFORM}` — Operating system platform name (`posix` on Linux/macOS, `nt` on Windows).

### 3. `settings`
Define configuration-wide defaults or reusable step templates:

```yaml
settings:
  xeet:
    default_step_type: exec
  common_steps:
    ping_server:
      type: exec
      cmd: "curl -s {api_host}/health"
      allowed_rc: [0]
      expected_stdout: "OK\n"
```

### 4. `tests`
A list of test descriptors.

#### Test Model Fields
| Field | Type | Description |
|---|---|---|
| `name` | `string` | Unique identifier for the test (`^[a-zA-Z0-9_-]+$`). |
| `base` | `string` | Name of another test to inherit from. |
| `abstract` | `boolean` | If `true`, the test cannot be run directly; only inherited by others. |
| `short_desc` | `string` | One-line description (displayed in listings). |
| `long_desc` | `string` | Detailed multi-line description (displayed in `info`). |
| `groups` | `list[string]` | Categorical tags used for filtering (`-g`, `-G`, `-X`). |
| `variables` | `dict` | Test-scoped variables overriding global variables. |
| `platforms` | `list[string]` | List of supported platforms (`posix`, `nt`). If set, test only runs on matching OS. |
| `pre_run` | `list[step]` | Setup steps executed before the main phase. |
| `run` | `list[step]` | Main test steps. |
| `post_run` | `list[step]` | Tear-down steps executed after the main phase. |
| `skip` | `boolean` | If `true`, marks the test to be skipped. |
| `skip_reason` | `string` | Reason displayed when skipped. |
| `expected_failure` | `boolean` | Inverts result (passes if execution fails, fails if it passes). |
| `pre_run_inheritance` | `prepend \| append \| replace` | How inherited `pre_run` steps are combined (default: `replace`). |
| `run_inheritance` | `prepend \| append \| replace` | How inherited `run` steps are combined (default: `replace`). |
| `post_run_inheritance` | `prepend \| append \| replace` | How inherited `post_run` steps are combined (default: `replace`). |

#### `exec` Step Fields
| Field | Type | Default | Description |
|---|---|---|---|
| `cmd` | `string` | (required) | Shell or process command to execute. |
| `base` | `string` | `""` | JSONPath reference to a base step (e.g. `settings.common_steps.ping_server`). |
| `cwd` | `string` | `null` | Working directory for the process. |
| `env` | `dict` | `{}` | Environment variables to inject into the process. |
| `env_file` | `string` | `null` | Path to a JSON file containing environment variables. |
| `use_os_env` | `boolean` | `false` | Pass through the host operating system's environment. |
| `use_shell` | `boolean` | `false` | Execute command via shell (alias: `shell`). |
| `shell_path` | `string` | `null` | Custom shell executable path. |
| `timeout` | `float` | `null` | Maximum execution time in seconds before terminating. |
| `allowed_rc` | `list[int] \| "*"` | `[0]` | Acceptable return codes (use `"*"` to accept any exit code). |
| `output_behavior` | `unify \| split` | `unify` | Combine stdout/stderr into one stream, or split them. |
| `stdout_file` | `string` | `"stdout"` | Output capture filename for stdout. |
| `stderr_file` | `string` | `"stderr"` | Output capture filename for stderr (when split). |
| `expected_stdout` | `string` | `null` | Literal string to match against stdout. |
| `expected_stdout_file` | `string` | `null` | File path containing expected stdout. |
| `expected_stderr` | `string` | `null` | Literal string to match against stderr. |
| `expected_stderr_file` | `string` | `null` | File path containing expected stderr. |
| `output_filters` | `list[filter]` | `[]` | Text scrubbers applied to output before comparison. |

---

## Inheritance Guide

`xeet` provides two distinct inheritance mechanisms: **Test-level inheritance** (for reusing setup phases, steps, and variables across tests) and **Step-level inheritance** (for sharing step definitions from a library or between tests).

### 1. Test Inheritance

A test can inherit from another test by specifying `base: <parent_test_name>`.

- **Variables**: Inherited by default (`inherit_variables: true`). A child test's `variables` override the parent's.
- **Platforms**: Inherited as a whole list if unset on the child. A child test can override its base's platforms list, or explicitly set `platforms: []` to clear an inherited restriction.
- **Phase Steps (`pre_run`, `run`, `post_run`)**: Combined according to the phase inheritance policy:
  - `replace` *(default)*: The child phase steps replace the parent's phase steps.
  - `append`: Parent steps execute first, followed by child steps.
  - `prepend`: Child steps execute first, followed by parent steps.
- **Abstract Tests**: Marked with `abstract: true`. Abstract tests cannot be run directly; they serve as templates for child tests and appear in `xeet list -a`.
- **Non-Inherited Attributes**: `short_desc`, `long_desc`, `skip`, and `expected_failure` are strictly test-specific and are deliberately never inherited.

#### Example: Abstract Base Test with Overrides and Appending

```yaml
tests:
  - name: base_api_test
    abstract: true
    variables:
      endpoint: "/health"
    pre_run:
      - cmd: "curl -s -X POST http://localhost:8080/setup"
    run:
      - cmd: "curl -s http://localhost:8080{endpoint}"
        expected_stdout: "{\"status\": \"ok\"}\n"
    post_run:
      - cmd: "curl -s -X POST http://localhost:8080/teardown"

  # Inherits setup, teardown, and overrides the endpoint variable
  - name: test_user_profile
    base: base_api_test
    short_desc: Verify user profile endpoint
    groups: [api, smoke]
    variables:
      endpoint: "/api/v1/profile"

  # Inherits base and appends an additional verification step
  - name: test_with_metrics
    base: base_api_test
    short_desc: Verify endpoint and check metrics
    run_inheritance: append
    run:
      - cmd: "curl -s http://localhost:8080/metrics"
        expected_stdout: "metrics_collected: true\n"
```

---

### 2. Step Inheritance

Individual steps can inherit from reusable step templates defined in `settings.common_steps` or from steps in other tests using **JSONPath** via `base: <jsonpath>`.

The derived step automatically inherits all attributes from the base step (command, working directory, environment, timeouts, expected outputs) while overriding any explicitly specified fields.

#### Example: Reusing Common Steps with Overrides

```yaml
settings:
  xeet:
    default_step_type: exec
  common_steps:
    # Base step template in the settings library
    run_python_script:
      type: exec
      cwd: "{XEET_ROOT}/scripts"
      env:
        PYTHONUNBUFFERED: "1"
      allowed_rc: [0]

tests:
  - name: data_processing
    run:
      # Inherits cwd, env, allowed_rc; specifies only cmd and expected output
      - base: "settings.common_steps.run_python_script"
        cmd: "python process.py --input data.csv"
        expected_stdout: "Processing complete.\n"

      # Re-uses the same template with custom environment override and timeout
      - base: "settings.common_steps.run_python_script"
        cmd: "python analyze.py"
        timeout: 10
        env:
          PYTHONUNBUFFERED: "1"
          ANALYSIS_MODE: "deep"
```

---

## Output Filtering

For hermetic testing, `output_filters` allow scrubbing machine-specific details (such as absolute paths or timestamps) before diffing against expected baselines:

```yaml
run:
  - cmd: "my_tool --report"
    expected_stdout_file: "baselines/report.txt"
    output_filters:
      - from_str: "{XEET_ROOT}"
        to_str: "__ROOT__"
      - from_str: "[0-9]+\\.[0-9]{3}s"
        to_str: "X.XXXs"
        regex: true
```

---

## Platform-Specific Testing

`xeet` supports cross-platform test suites by allowing tests to restrict execution to specific operating systems (`posix` for Linux/macOS, `nt` for Windows) and by providing the `{XEET_PLATFORM}` auto-variable for conditional file inclusion.

### 1. Declaring Supported Platforms

Use the `platforms` field to restrict a test or an abstract base test to matching operating systems. Tests that do not match the host platform are automatically reported as `Skipped`:

```yaml
tests:
  - name: test_posix_permissions
    platforms: [posix]
    run:
      - cmd: "ls -la /tmp"

  - name: test_windows_registry
    platforms: [nt]
    run:
      - cmd: "powershell -Command Get-ItemProperty 'HKCU:\\Software'"
```

### 2. Platform-Conditional Configuration Includes

Use `{XEET_PLATFORM}` in `include` directives to dynamically load OS-specific step libraries and variable definitions:

```yaml
# Automatically loads 'xeet_posix.yaml' on Linux/macOS or 'xeet_nt.yaml' on Windows
include:
  - "common_steps.yaml"
  - "xeet_{XEET_PLATFORM}.yaml"

tests:
  - name: run_service
    base: platform_service_step
```

---

## Command-Line Usage

### Running Tests

```bash
# Run all tests in the default config (xeet.yaml)
xeet run

# Run with a specific configuration file
xeet run -c path/to/config.yaml

# Run specific tests by exact name or fuzzy pattern
xeet run -t test_name
xeet run -z smoke

# Filter by groups
xeet run -g integration              # Include any test in group 'integration'
xeet run -G api -G v2                # Require tests to belong to both 'api' AND 'v2'
xeet run -X slow                     # Exclude tests in group 'slow'

# Repeat execution (multi-iteration testing)
xeet run -r 5

# Parallel execution across worker threads
xeet run -j                          # Auto-detects half of CPU cores
xeet run -j 4                        # Run with 4 concurrent worker threads

# Control output verbosity
xeet run --verbose                   # Detailed per-test output, timings, criteria
xeet run --concise                   # Compact single-line output
xeet run --quiet                     # Minimal output
xeet run --debug                     # Live real-time process tailing and event logs

# Custom output directory for test artifacts
xeet run -O /path/to/artifacts
```

### Inspecting Suites & Tests

```bash
# List all tests and one-line descriptions
xeet list

# List all tests including abstract base tests
xeet list -a

# List all available test groups
xeet groups

# Show detailed information about a test definition
xeet info -t my_test

# Show test information with resolved variables and full step details
xeet info -t my_test -x -f
```

### Exporting & Schema Generation

```bash
# Dump the resolved JSON schema for IDE validation
xeet dump schema -t config
xeet dump schema -t test
xeet dump schema -t unified

# Dump a specific test descriptor in YAML
xeet dump test -t my_test

# Query and dump configuration sections using JSONPath
xeet dump config -p "settings.common_steps"
```

---

## Exit Codes

`xeet` returns composite exit codes to facilitate CI/CD integration:

- `0` — All selected tests ran and passed.
- `1` — One or more tests failed.
- `2` — One or more tests could not be run (e.g. `pre_run` error or invalid command).
- `3` — Both test failures and unrunnable tests occurred (`1 + 2`).

---

## License

This project is licensed under the **GNU Affero General Public License v3.0** (AGPL-3.0). See the [LICENSE](LICENSE) file for details.
