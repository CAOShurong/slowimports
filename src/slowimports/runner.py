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

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

__all__ = ["RunResult", "RunnerError", "Target", "run_profile"]


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


def _console_script_module(command: str) -> str | None:
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

    # Windows wrappers are zip-embedded executables; the console script's own
    # source is not readable this way.
    if blob[:2] == b"MZ":
        return None
    try:
        text = blob.decode("utf-8", errors="replace")
    except Exception:
        return None

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
        module = _console_script_module(target.value)
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
        target = Target("code", f"import {module}", target.args)

    argv = target.interpreter_argv(python)
    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    # Bytecode writing is one-off work that would land in whichever module
    # happened to be compiled first, so it is disabled for a fair measurement.
    run_env.setdefault("PYTHONDONTWRITEBYTECODE", "1")

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
