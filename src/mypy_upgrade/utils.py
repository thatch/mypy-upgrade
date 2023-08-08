# remove when dropping Python 3.7-3.9 support
from __future__ import annotations

import io
import tokenize
from collections.abc import Iterable
from typing import NamedTuple, TextIO

from mypy_upgrade.parsing import MypyError


class UnsilenceableRegion(NamedTuple):
    """A region within a source code that cannot be silenced by an inline
    comment.

    Attributes:
        start: a 2-tuple representing the start of the unsilenceable region
            whose first entry is the start line (1-indexed) and whose second
            entry is the start column offset.
        end: a 2-tuple representing the end of the unsilenceable region
            whose first entry is the end line (1-indexed) and whose second
            entry is the end column offset.

        When start[0] = end[0], it is interpreted that the Unsilenceable
        region is an explicitly continued line.
    """

    start: tuple[int, int]  # line, column
    end: tuple[int, int]  # line, column


def split_code_and_comment(line: str) -> tuple[str, str]:
    """Split a line of code into the code part and comment part."""
    reader = io.StringIO(line).readline

    try:
        comment_tokens = []
        for t in tokenize.generate_tokens(reader):
            if t.type == tokenize.COMMENT:
                comment_tokens.append(t)

        if not comment_tokens:
            return line.rstrip(), ""

        comment_token = comment_tokens[0]
        python_code = line[0 : comment_token.start[1]]
        python_comment = line[comment_token.start[1] :]
    except tokenize.TokenError:  # compromise for multi-line statements
        comment_start = line.find("#")
        if comment_start >= 0:
            python_code = line[0:comment_start]
            python_comment = line[comment_start:]
        else:
            python_code, python_comment = (line, "")

    return python_code.rstrip(), python_comment


def find_unsilenceable_regions(stream: TextIO) -> list[UnsilenceableRegion]:
    """Find the regions encapsulated by line continuation characters or
    by multiline strings

    Args:
        stream: A text stream.

    Returns:
        A list of UnsilenceableRegion objects.

        Multiline strings are represented by UnsilienceableRegion objects
        whose first entries in their `start` and `end` attributes are
        different. Explicitly continued lines are represented by
        UnsilienceableRegion objects whose first entries in their `start` and
        `end` attributes are the same.
    """
    all_lines = list(tokenize.generate_tokens(stream.readline))
    unsilenceable_regions = []
    for token in all_lines:
        if (
            token.start[0] != token.end[0]
            and token.exact_type == tokenize.STRING
        ):
            region = UnsilenceableRegion(token.start, token.end)
            unsilenceable_regions.append(region)

    comments = [t for t in all_lines if t.exact_type == tokenize.COMMENT]

    for token in all_lines:
        if token.line.rstrip("\r\n").endswith("\\") and not any(
            comment.line == token.line for comment in comments
        ):
            start = token.end[0], 0
            end = token.end[0], len(token.line)
            region = UnsilenceableRegion(start, end)
            unsilenceable_regions.append(region)

    return unsilenceable_regions


def find_safe_end_line(
    error: MypyError, unsilenceable_regions: Iterable[UnsilenceableRegion]
) -> int:
    """Find a syntax-safe line on which to place an error suppression comment
    for the given error.

    Args:
        error: a `MypyError` for which a type error suppression comment is to
            placed.
        unsilenceable_regions: an `Iterable` in which each entry is an
            `UnsilenceableRegion`.

    Returns:
        An integer representing a safe line on which to place an error
        suppression comment if it exists. If no safe line exists, this method
        returns -1.
    """
    new_line = None
    new_col_offset = None
    for region in unsilenceable_regions:
        # It is safe to comment the last line of a multiline string
        if error.line_no == region.end[0] and region.start[0] != region.end[0]:
            continue

        # It is indeterminant whether an error within an UnsilenceableRegion
        # can be suppressed if its column number is unknown
        if (
            error.col_offset is None
            and region.start[0] <= error.line_no <= region.end[0]
        ):
            return -1

        if (
            error.col_offset is not None
            and region.start <= (error.line_no, error.col_offset) <= region.end
        ):
            return -1

        # Error precedes same line multiline string
        if (
            error.line_no == region.start[0]
            and region.start[0] != region.end[0]
        ):
            new_line = region.end[0]
            new_col_offset = int(region.end[1])

    if new_line is None:
        return error.line_no

    new_error = MypyError(
        error.filename,
        new_line,
        new_col_offset,
        error.message,
        error.error_code,
    )
    return find_safe_end_line(new_error, unsilenceable_regions)


def correct_line_numbers(
    stream: TextIO, errors: Iterable[MypyError]
) -> tuple[list[MypyError], list[MypyError]]:
    """Correct the line numbers of MypyErrors considering multiline statements.

    Args:
        stream: A text stream from which the line numbers of provided errors
            are to be corrected.
        errors: The errors whose line numbers are to be corrected.

    Returns:
        A 2-tuple whose first entry is a list in which each entry is a
        `MypyError` from `errors` for which type suppression comments can be
        added (with line numbers corrected) and whose second entry is a list
        of each `MypyError` that cannot be silenced.
    """
    unsilenceable_regions = find_unsilenceable_regions(stream)
    line_corrected_errors = []
    unsilenceable_errors = []
    for error in errors:
        end_line = find_safe_end_line(error, unsilenceable_regions)

        if end_line == -1:
            unsilenceable_errors.append(error)
        else:
            line_corrected_errors.append(
                MypyError(
                    error.filename,
                    end_line,
                    error.col_offset,
                    error.message,
                    error.error_code,
                )
            )

    return line_corrected_errors, unsilenceable_errors
