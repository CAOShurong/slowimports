"""Run the thing being measured.

Four kinds of target, because these are the four ways people start Python:
a script, ``-m module``, ``-c code``, and an installed console script. The
last one matters most in practice -- "my CLI takes a second to print
``--help``" is the complaint this tool exists for -- and it needs handling
because a console script is a generated wrapper, not something you can
import.

Measurement runs in a subprocess with ``-X importtime``. It has to: the
interpreter can only report import times for imports it has not already
done, and by the time this code is running, half the standard library is
loaded.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import zipfile
from contextlib import suppress
from dataclasses import dataclass

__all__ = ["RunResult", "RunnerError", "Target", "run_profile"]


_ENTRY_POINT_MARKER = "slowimports-entry-point:"
_ENTRY_POINT_PROBE = r"""
import json
import os
import sys
import sysconfig
from importlib.metadata import distributions

name = sys.argv[1].casefold()
command_dir = os.path.normcase(os.path.realpath(os.path.dirname(sys.argv[2])))
scripts_dir = os.path.normcase(os.path.realpath(sysconfig.get_path("scripts") or ""))
matches = []
for distribution in distributions():
    for entry_point in distribution.entry_points:
        if entry_point.group != "console_scripts":
            continue
        if entry_point.name.casefold() != name:
            continue
        matches.append(
            {
                "distribution": distribution.metadata.get("Name", "unknown"),
                "module": entry_point.value.partition(":")[0].strip(),
            }
        )
print(
    "slowimports-entry-point:"
    + json.dumps(
        {
            "command_dir": command_dir,
            "scripts_dir": scripts_dir,
            "matches": matches,
        }
    )
)
"""


class RunnerError(RuntimeError):
    """The target could not be run at all."""


@dataclass
class RunResult:
    """What came back from the measured process."""

    stderr: str
    stdout: str
    returncode: int
    argv: list[str]

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass
class Target:
    """A thing to measure, in a form the interpreter will accept."""

    kind: str  # "script" | "module" | "code" | "console"
    value: str
    args: list[str]

    def describe(self) -> str:
        base = {
            "script": self.value,
            "module": f"-m {self.value}",
            "code": f"-c {self.value!r}",
            "console": self.value,
        }[self.kind]
        return " ".join([base, *self.args]) if self.args else base

    def interpreter_argv(self, python: str) -> list[str]:
        if self.kind == "script":
            return [python, "-X", "importtime", self.value, *self.args]
        if self.kind == "module":
            return [python, "-X", "importtime", "-m", self.value, *self.args]
        if self.kind == "code":
            return [python, "-X", "importtime", "-c", self.value, *self.args]
        raise AssertionError(f"console targets are rewritten before this point: {self}")


def resolve(raw: str, args: list[str], *, kind: str | None = None) -> Target:
    """Work out what the user meant by ``raw``.

    Explicit beats inferred, and the inference only fires when it is
    unambiguous: an existing ``.py`` file is a script, a name on PATH is a
    console script, and anything else is treated as a module so that
    ``slowimports pytest`` does the obvious thing.
    """
    if kind == "code":
        return Target("code", raw, args)
    if kind == "module":
        return Target("module", raw, args)
    if kind == "script":
        return Target("script", raw, args)

    if raw.endswith(".py") or os.path.sep in raw or (os.altsep and os.altsep in raw):
        return Target("script", raw, args)
    if shutil.which(raw):
        return Target("console", raw, args)
    return Target("module", raw, args)


def _console_script_from_metadata(
    command: str,
    path: str,
    python: str,
    *,
    timeout: float,
) -> str | None:
    """Resolve an opaque launcher through the selected Python's metadata.

    Modern Windows installers use a native ``.exe`` launcher, so there is no
    wrapper source to read. Querying ``console_scripts`` metadata is the
    portable alternative, but only when the command lives in that
    interpreter's scripts directory. Otherwise a same-named entry point from
    another environment could make us silently profile the wrong module.

    The query runs in a separate process. It reads metadata only: the entry
    point's callable is never loaded or invoked.
    """
    name = os.path.basename(command)
    if name.casefold().endswith(".exe"):
        name = name[:-4]
    resolution_timeout = min(max(timeout, 1.0), 15.0)
    try:
        completed = subprocess.run(
            [python, "-c", _ENTRY_POINT_PROBE, name, os.path.abspath(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=resolution_timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RunnerError(f"could not run {python!r}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RunnerError(
            f"could not query console-script metadata with {python!r} "
            f"within {resolution_timeout:g}s"
        ) from exc

    payload = None
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith(_ENTRY_POINT_MARKER):
            with suppress(ValueError):
                payload = json.loads(line[len(_ENTRY_POINT_MARKER) :])
            break
    if completed.returncode != 0 or not isinstance(payload, dict):
        raise RunnerError(
            f"could not query console-script metadata with {python!r} "
            f"(exit code {completed.returncode})"
        )

    command_dir = payload.get("command_dir")
    scripts_dir = payload.get("scripts_dir")
    if not command_dir or command_dir != scripts_dir:
        raise RunnerError(
            f"console script {command!r} is in {command_dir or 'an unknown directory'}, "
            f"but {python!r} installs scripts in {scripts_dir or 'an unknown directory'}.\n"
            "  Use --python with the interpreter that installed the command."
        )

    matches = payload.get("matches")
    if not isinstance(matches, list) or not matches:
        return None
    if len(matches) != 1:
        providers = ", ".join(
            str(match.get("distribution", "unknown"))
            for match in matches
            if isinstance(match, dict)
        )
        raise RunnerError(
            f"console script {command!r} is declared by multiple distributions: "
            f"{providers or 'unknown'}.\n"
            "  Refusing to guess which module the launcher imports."
        )

    match = matches[0]
    module = match.get("module") if isinstance(match, dict) else None
    return module if isinstance(module, str) and module else None


def _console_script_module(
    command: str,
    python: str,
    *,
    timeout: float,
) -> str | None:
    """Find the module a console script would run, without running it.

    Entry-point wrappers are generated files that import a function and call
    it. Reading the wrapper is enough to recover the module, which can then be
    measured with ``-m``-style semantics -- and importantly *without*
    executing the tool's main function, which might do real work.
    """
    path = shutil.which(command)
    if path is None:
        return None
    try:
        with open(path, "rb") as handle:
            blob = handle.read(8192)
    except OSError:
        return None

    # Windows wrappers are zip-embedded executables; their Python source is
    # not readable as the leading MZ bytes. zipfile can read the embedded
    # __main__.py used by distlib, including versioned aliases such as
    # pip3.13 that installers generate without declaring another entry point.
    # Standard metadata remains the portable fallback for other launchers.
    if blob[:2] == b"MZ":
        wrapper_module = _console_script_zip_module(path)
        metadata_module = _console_script_from_metadata(command, path, python, timeout=timeout)
        if wrapper_module and metadata_module and wrapper_module != metadata_module:
            raise RunnerError(
                f"console script {command!r} imports {wrapper_module!r}, but its "
                f"package metadata declares {metadata_module!r}.\n"
                "  Refusing to profile conflicting launcher data."
            )
        return wrapper_module or metadata_module
    try:
        text = blob.decode("utf-8", errors="replace")
    except Exception:
        return None

    return _module_from_wrapper(text)


def _console_script_zip_module(path: str) -> str | None:
    """Read the bounded Python wrapper embedded in a distlib launcher."""
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo("__main__.py")
            if info.file_size > 64 * 1024:
                return None
            text = archive.read(info).decode("utf-8", errors="replace")
    except (KeyError, OSError, RuntimeError, zipfile.BadZipFile):
        return None
    return _module_from_wrapper(text)


def _module_from_wrapper(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("from ") and " import " in line:
            module = line.split()[1]
            if module and not module.startswith("_"):
                return module
    return None


def run_profile(
    target: Target,
    *,
    python: str | None = None,
    timeout: float = 120.0,
    env: dict[str, str] | None = None,
) -> RunResult:
    """Execute ``target`` under ``-X importtime`` and capture its stderr."""
    python = python or sys.executable

    if target.kind == "console":
        module = _console_script_module(target.value, python, timeout=timeout)
        if module is None:
            raise RunnerError(
                f"Could not read the console script {target.value!r} to find its "
                "module.\n"
                f"  Try:  slowimports -m <module>    (the package that provides "
                f"{target.value})"
            )
        # Import the module without running it: the question is what importing
        # costs, and running the tool's main function would measure something
        # else entirely, possibly with side effects.
        # __import__ takes a quoted string, so locally modified metadata cannot
        # inject code into the command used for measurement.
        target = Target("code", f"__import__({module!r})", target.args)

    argv = target.interpreter_argv(python)
    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    # Bytecode writing is one-off work that would land in whichever module
    # happened to be compiled first, so it is disabled for a fair measurement.
    run_env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    # The target writes into pipes that we decode as UTF-8 below. On Windows,
    # Python otherwise chooses the locale encoding for a pipe, which can make
    # an otherwise successful target fail merely for printing Unicode. Honour
    # an explicit caller choice, but make our encoder and decoder agree by
    # default.
    run_env.setdefault("PYTHONIOENCODING", "utf-8")

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=run_env,
        )
    except FileNotFoundError as exc:
        raise RunnerError(f"could not run {argv[0]!r}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RunnerError(
            f"{target.describe()} did not finish within {timeout:.0f}s.\n"
            "  If it is a long-running program, measure its import instead:\n"
            f"  slowimports -c 'import <the module>'"
        ) from exc

    return RunResult(
        stderr=completed.stderr or "",
        stdout=completed.stdout or "",
        returncode=completed.returncode,
        argv=argv,
    )
