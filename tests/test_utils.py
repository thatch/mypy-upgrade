from __future__ import annotations

import io
import sys
import tokenize

import pytest

from mypy_upgrade.utils import (
    find_unsilenceable_lines,
    split_code_and_comment,
)

CODE_LINES = [
    "x = 5\n",
    "if x == '4':\n",
    "\n",
    "This has an empty comment#\n",
    "This has an empty comment #\n",
    "This has a comment# here\n",
    "This has a comment # here\n",
    "This has one comment that looks like two # here # and here\n",
]

CODE_AND_COMMENTS = [
    ("x = 5\n", ""),
    ("if x == '4':\n", ""),
    ("\n", ""),
    ("This has an empty comment", "#\n"),
    ("This has an empty comment ", "#\n"),
    ("This has a comment", "# here\n"),
    ("This has a comment ", "# here\n"),
    ("This has one comment that looks like two ", "# here # and here\n"),
]


class TestSplitCodeAndComment:
    if sys.version_info < (3, 10):
        CODE_LINES_AND_CODE_AND_COMMENTS = zip(CODE_LINES, CODE_AND_COMMENTS)
    else:
        CODE_LINES_AND_CODE_AND_COMMENTS = zip(
            CODE_LINES, CODE_AND_COMMENTS, strict=True
        )

    @staticmethod
    @pytest.mark.parametrize(
        ("code_line", "code_and_comment"),
        CODE_LINES_AND_CODE_AND_COMMENTS,
    )
    def test_should_split_lines_into_code_and_comment_correctly(
        code_line: str, code_and_comment: tuple[str, str]
    ) -> None:
        split = split_code_and_comment(code_line)
        stripped_code_and_comment = (
            code_and_comment[0].strip(),
            code_and_comment[1],
        )
        assert split == stripped_code_and_comment


class TestFindUnsilenceableLines:
    @staticmethod
    def test_should_return_tokens_on_explicitly_continued_lines():
        code = "\n".join(
            [
                "x = 1+\\",
                "1",
                "if x == 4:",
                "    return True",
            ]
        )
        stream = io.StringIO(code)
        tokens = find_unsilenceable_lines(stream)
        assert any(token.end[0] == 1 for token in tokens)

    @staticmethod
    def test_should_only_return_string_token_for_explicitly_continued_string():
        code = "\n".join(
            [
                "x = '\\",
                "1'",
            ]
        )
        stream = io.StringIO(code)
        tokens = find_unsilenceable_lines(stream)
        assert all(token.exact_type == tokenize.STRING for token in tokens)

    @staticmethod
    def test_should_return_tokens_in_multiline_strings1():
        code = "\n".join(
            [
                "x = '''Hi,",
                "this is a multiline",
                "string'''",
            ]
        )
        stream = io.StringIO(code)
        tokens = find_unsilenceable_lines(stream)
        assert any(t.start[0] == 1 for t in tokens)
        assert any(t.end[0] == 3 for t in tokens)

    @staticmethod
    def test_should_return_tokens_in_multiline_strings2():
        code = "\n".join(
            [
                "comment = '\\",
                "this is a\\",
                "multiline string'",
            ]
        )
        stream = io.StringIO(code)
        tokens = find_unsilenceable_lines(stream)
        assert any(t.start[0] == 1 for t in tokens)
        assert any(t.end[0] == 3 for t in tokens)
