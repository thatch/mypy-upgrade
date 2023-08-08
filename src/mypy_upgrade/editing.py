# remove when dropping Python 3.7-3.9 support
from __future__ import annotations

import re
from collections.abc import Iterable


def add_type_ignore_comment(comment: str, error_codes: list[str]) -> str:
    """Add type ignore comment with error codes to in-line comment.

    Args:
        comment: A comment in which to add a type ignore comment.
        error_codes: The error codes to add to the type ignore comment.

    Returns:
        A copy of the comment with a "type: ignore[error-code]" comment
    """
    old_type_ignore_re = re.compile(
        r"type\s*:\s*ignore\[(?P<error_code>[a-z, \-]+)\]"
    )

    # Handle existing "type: ignore[error_code]" comments
    match = old_type_ignore_re.search(comment)
    if match:
        old_error_codes = set(
            match.group("error_code").replace(" ", "").split(",")
        )
        error_codes.extend(e for e in old_error_codes if e not in error_codes)
        comment = old_type_ignore_re.sub("", comment)

        # Check for other comments; otherwise, remove comment
        if not re.search(r"[^#\s]", comment):
            comment = ""
        else:
            comment = f' # {comment.lstrip("# ")}'
    elif comment:
        # format comment
        comment = f' # {comment.lstrip("# ")}'

    sorted_error_codes = ", ".join(sorted(error_codes))

    return f"# type: ignore[{sorted_error_codes}]{comment}"


def format_type_ignore_comment(comment: str) -> str:
    """Remove excess whitespace and commas from `"type: ignore"` comments."""
    type_ignore_re = re.compile(
        r"type\s*:\s*ignore(\[(?P<error_codes>[a-z, \-]+)\])?"
    )
    match = type_ignore_re.search(comment)

    # Format existing error codes
    if match:
        error_codes = match.group("error_codes")
        if error_codes:
            pruned_error_codes = []
            for code in error_codes.split(","):
                pruned_code = code.strip()
                if pruned_code:
                    pruned_error_codes.append(pruned_code)

            formatted_comment = comment.replace(
                error_codes, ", ".join(pruned_error_codes)
            )
            if pruned_error_codes:
                return formatted_comment

            # Format again if there are no error codes
            return format_type_ignore_comment(formatted_comment)

    # Delete "type: ignore", "type: ignore[]"
    formatted_comment = re.sub(r"type\s*:\s*ignore\s*(\[\])?", "", comment)

    # Return empty string if nothing is left in the comment
    if not re.search(r"[^#\s]", formatted_comment):
        return ""

    return formatted_comment


def remove_unused_type_ignore(
    comment: str, codes_to_remove: Iterable[str]
) -> str:
    """Remove specified error codes from a comment string.

    Args:
        comment: a string whose "type: ignore" codes are to be removed.
        codes_to_remove: an iterable of strings which represent mypy error
            codes. If this iterable is length zero, the entire "type: ignore"
            comment is removed.

    Returns:
        A copy of the original string with the specified error codes removed.
    """
    if codes_to_remove:
        pruned_comment = comment
        for code_to_remove in codes_to_remove:
            pruned_comment = pruned_comment.replace(code_to_remove, "")
    else:
        pruned_comment = re.sub(
            r"type\s*:\s*ignore(\[[a-z, \-]+\])?", "", comment
        )

    return pruned_comment
