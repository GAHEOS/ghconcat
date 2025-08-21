from __future__ import annotations

from typing import List


def strip_dart_comments(source: str) -> str:
    """
    Remove all Dart comments from *source* while preserving string literals.

    Supported:
      - Line comments: `//` and `///` (removed until end-of-line; handles CRLF).
      - Block comments: `/* ... */`, `/** ... */`, `/*** ... */` with **nesting**.
      - Strings (never stripped inside):
          * Single/double: '...', "..."
          * Triple multiline: '''...''', \"\"\"...\"\"\"
          * Raw: r'...', r"...", r'''...''', r\"\"\"...\"\"\"

    Implementation:
      Deterministic single-pass state machine:
        code | line_comment | block_comment(depth) | string(raw, triple, quote)

    Notes:
      - After closing a block comment in code, we append one space if needed to
        avoid token concatenation (e.g., `a/*x*/b` → `a b`).
    """
    out: list[str] = []
    n = len(source)
    i = 0

    # Block comment nesting level
    depth = 0

    # String state
    in_string = False
    is_raw = False
    is_triple = False
    quote = ""   # "'" or '"'

    last_out = ""  # last emitted char

    def starts(s: str, pos: int) -> bool:
        return 0 <= pos <= n - len(s) and source.startswith(s, pos)

    def ch(pos: int) -> str:
        return source[pos] if 0 <= pos < n else ""

    def write(s: str) -> None:
        nonlocal last_out
        if s:
            out.append(s)
            last_out = s[-1]

    def write_ch(c: str) -> None:
        nonlocal last_out
        out.append(c)
        last_out = c

    def append_space_once() -> None:
        """Append one space if `last_out` is not whitespace/punct."""
        if not last_out:
            return
        if last_out in " \t\r\n":
            return
        if last_out in "()[]{};,.:+-*/%&|^!<>=?~":
            return
        write_ch(" ")

    while i < n:
        # --------------- block comment ---------------
        if depth > 0:
            # Support nested opens
            if starts("/*", i):
                depth += 1
                i += 2
                continue
            # Closing
            if starts("*/", i):
                depth -= 1
                i += 2
                if depth == 0:
                    append_space_once()
                continue
            # Skip any char inside the block (including newlines)
            i += 1
            continue

        # --------------- not in string ---------------
        if not in_string:
            # Line comment (// or ///) — remove until EOL, keep EOL
            if starts("//", i):
                i += 2
                # Skip until end-of-line
                while i < n and source[i] not in "\r\n":
                    i += 1
                # Preserve newline properly (CRLF or LF)
                if i < n:
                    if source[i] == "\r" and i + 1 < n and source[i + 1] == "\n":
                        write("\r\n")
                        i += 2
                    elif source[i] in "\r\n":
                        write_ch(source[i])
                        i += 1
                continue

            # Block comment: handles /* ... */, /** ... */, /*** ... */
            if starts("/*", i):
                depth = 1
                i += 2
                continue

            # Raw string? r'...' / r"..." / r'''...''' / r\"\"\"...\"\"\"
            if ch(i) in ("r", "R") and ch(i + 1) in ("'", '"'):
                is_raw = True
                quote = ch(i + 1)
                is_triple = ch(i + 2) == quote and ch(i + 3) == quote
                if is_triple:
                    write(f"{ch(i)}{quote * 3}")  # r + ''' or r + """
                    i += 4
                else:
                    write(f"{ch(i)}{quote}")      # r + ' or r + "
                    i += 2
                in_string = True
                continue

            # Normal string? ' or "
            if ch(i) in ("'", '"'):
                is_raw = False
                quote = ch(i)
                is_triple = ch(i + 1) == quote and ch(i + 2) == quote
                if is_triple:
                    write(quote * 3)
                    i += 3
                else:
                    write_ch(quote)
                    i += 1
                in_string = True
                continue

            # Plain code
            write_ch(ch(i))
            i += 1
            continue

        # --------------- inside string ---------------
        if is_triple:
            if is_raw:
                if starts(quote * 3, i):
                    write(quote * 3)
                    i += 3
                    in_string = False
                    is_triple = False
                    is_raw = False
                else:
                    write_ch(ch(i))
                    i += 1
                continue

            # Non-raw triple: handle escapes
            if ch(i) == "\\":
                write_ch("\\")
                if i + 1 < n:
                    write_ch(ch(i + 1))
                    i += 2
                else:
                    i += 1
                continue

            if starts(quote * 3, i):
                write(quote * 3)
                i += 3
                in_string = False
                is_triple = False
                is_raw = False
                continue

            write_ch(ch(i))
            i += 1
            continue

        # Single-line string
        if is_raw:
            if ch(i) == quote:
                write_ch(quote)
                i += 1
                in_string = False
                is_raw = False
            else:
                write_ch(ch(i))
                i += 1
            continue

        # Non-raw single-line: escapes
        if ch(i) == "\\":
            write_ch("\\")
            if i + 1 < n:
                write_ch(ch(i + 1))
                i += 2
            else:
                i += 1
            continue

        if ch(i) == quote:
            write_ch(quote)
            i += 1
            in_string = False
            continue

        write_ch(ch(i))
        i += 1

    return "".join(out)