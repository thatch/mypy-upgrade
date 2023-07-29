#!/usr/bin/env python3

"""This defines a tool to silence mypy errors using in-line comments.


Usage::

    $ mypy path/to/project | pythom -m mypy-upgrade <package>
"""

import argparse
import importlib
import io
import pathlib
import re
import subprocess
import sys
import tempfile
import typing
from abc import ABC
from collections.abc import Iterable
from importlib import util


class Consume(argparse.Action, ABC):
    def __init__(self, option_strings, dest, **kwargs) -> None:
        super().__init__(option_strings, dest, **kwargs)

    def __call__(
        self, parser, namespace, values, option_string=None  # noqa: ARG002
    ):
        try:
            sys.argv.remove(option_string)
            sys.argv.remove(values)
        except ValueError:
            try:
                sys.argv.remove(values)
            except ValueError:
                pass


class Split(Consume):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, values.split(","))
        super().__call__(parser, namespace, values, option_string)


class StorePath(Consume):
    def __call__(self, parser, namespace, values, option_string=None):
        file = pathlib.Path(values)
        if not file.exists():
            msg = f"{file} does not exist."
            raise FileNotFoundError(msg)
        setattr(namespace, self.dest, file)
        super().__call__(parser, namespace, values, option_string)


def open_report_file(file: str | None) -> typing.IO:
    """Obtain mypy type checking report file.

    If no file is supplied, this function attempts to read from stdin.
    If an error occurs trying to read from stdin, this function calls mypy
    Args:
        file: a string representing the path to a report file. Defaults to
        None.

    Returns:
        A file stream corresponding to the report file.
    """
    if file:
        return open(file, encoding="utf-8")

    if sys.argv[:1] and "checked" in sys.argv[-1]:
        return io.StringIO(sys.argv[-1])

    temp = tempfile.NamedTemporaryFile(mode="r+", encoding="utf-8")
    _ = subprocess.run(
        ["python", "-m", "mypy", "."], stderr=subprocess.STDOUT, stdout=temp  # noqa: S603, S607
    )
    _ = temp.seek(0)
    return temp


def parse_report(
    report: typing.TextIO,
) -> list[tuple[str, int, str, str]]:
    """Parse a mypy error report from stdin.

    Args:
        report: a text stream from which to read the mypy typing report
    Returns:
        A list of four-tuples which represent a mypy error. The elements of
        the tuple are as follows:
            0) a string representing the path to module containing the error
            1) an int representing the line number of the error
            2) a string representing the mypy error code
            3) a string describing the error
        Note that the line numbers are 1-indexed.

        Example::

           >> errors = process_report('ase')
           >> module, line_no, error_code, description = errors[0]
    """
    # captures:
    # 1) file path to module
    # 2) line number
    # 3) error description
    # 4) error code
    info = re.compile(r"^([^:]+):(\d+): error: (.+)\s+\[(.+)\]$")
    errors = []

    for line in report:
        package_error = info.match(line)
        if package_error:
            module, description, error_code = package_error.group(1, 3, 4)
            line_no = int(package_error.group(2))
            errors.append((module, line_no, error_code, description))

    return errors


def get_module_paths(modules: list[str]) -> list[pathlib.Path | None]:
    """Determine file system paths of given modules/packages.

    Args:
        modules: a list of strings representing modules.

    Returns:
        A list (of the same length as the input list) of pathlib.Path objects
        corresponding to the given modules. If a path is not found for a
        module, the corresponding entry in the output is ``None``.
    """
    paths: list[pathlib.Path | None] = []
    for module in modules:
        spec = util.find_spec(module)
        if spec is None:
            paths.append(None)
        else:
            origin = spec.origin
            if spec.submodule_search_locations:  # Package
                if origin is None:  # Namespace
                    module_path = pathlib.Path(spec.submodule_search_locations[0])
                else:  # Regular
                    module_path = pathlib.Path(origin.removesuffix("__init__.py"))
            elif origin is None:  # Something weird has happened
                module_path = None
            else:
                module_path = pathlib.Path(origin)

            paths.append(module_path)

    return paths


def select_errors(
    errors: list[tuple[str, int, str, str]],
    packages: list[str],
    modules: list[str],
    files: list[str],
) -> list[tuple[str, int, str, str]]:
    """Select errors based on specified packages, modules, files.

    Args:
        packages: a list of strings specifying packages to be included.
        modules: a list of strings specifying modules to be included.
        files: a list of strings specifying files to be included.

    Returns:
        A list of errors including only those in either packages, modules, or
        files.
    """
    package_paths = [p for p in get_module_paths(packages) if p is not None]
    module_paths = get_module_paths(modules)
    paths = [pathlib.Path(f) for f in files] + module_paths
    filtered = []
    for module, line_no, error_code, description in errors:
        module_path = pathlib.Path(module).resolve()
        included_file = module_path in paths
        in_package = False

        for package in package_paths:
            if pathlib.Path(module).is_relative_to(package):
                in_package = True
                break

        if (in_package or included_file):
            filtered.append((module, line_no, error_code, description))

    return filtered


def silence_errors(
    module: str, line_no: int, error_code: str, description: str
):
    """Silences all errors in a given file.

    Args:
        module: a string representing the path to the module with the errors
            to fix.
        errors: a dictionary representing the errors in a module in the same
            format as the values of the return vale of `process_piped_report`.
    """
    with open(module, encoding="utf-8") as f:
        lines = f.readlines()

    line = lines[line_no - 1].removesuffix("\n")
    comment = f"# type: ignore[{error_code}]  # {description}"
    lines[line_no - 1] = f"{line}  {comment}\n"

    with open(module, "w", encoding="utf-8") as f:
        _ = f.write("".join(lines))


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="mypy-upgrade",
        description="Place in-line comments into files to silence mypy errors",
        epilog="""
Usage::

    $ mypy /path/to/project | python -m mypy-upgrade --packages <package>[,<package>]
    $ python -m mypy-upgrade --report mypy_report.txt --packages <package>[,<package>]
    $ python -m mypy-upgrade --packages <package>[,<package>]
""",
    )
    parser.add_argument(
        "--files",
        default=[],
        action=Split,
        help="A comma-separated list of files for which errors will be "
        "suppressed.",
    )
    parser.add_argument(
        "--modules",
        default=[],
        action=Split,
        help="A comma-separated list of modules for which errors will be "
        "suppressed. The modules must be importable.",
    )
    parser.add_argument(
        "--packages",
        default=[],
        action=Split,
        help="A comma-separated list of packages for which errors will be "
        "suppressed. The packages must be importable.",
    )
    parser.add_argument(
        "--report",
        action=StorePath,
        help="The path to a text file containing a mypy type checking report.",
    )
    return parser.parse_args()


def main():
    """Logic for CLI."""
    args = _parse_arguments()
    with open_report_file(args.report) as report:
        errors = parse_report(report)

    #filtered = filter_errors(errors, args.packages, args.modules, args.files)
    modules = []
    for module, line_no, error_code, description in errors:
        silence_errors(module, line_no, error_code, description)
        if module not in modules:
            modules.append(module)

    print(  # noqa: T201
        f"{len(errors)} errors silenced across {len(modules)} modules."
    )


if __name__ == "__main__":
    main()
