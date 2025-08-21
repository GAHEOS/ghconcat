"""
py_docstrip – Python comment and docstring stripping via AST.

This module provides a safe, production-ready function to strip Python
docstrings and (by virtue of `ast.unparse`) drop all '#' comments.
It also ensures classes/functions/modules keep syntactically valid bodies
by inserting a `pass` statement when a sole docstring is removed.

Notes
-----
• Requires Python ≥ 3.9 for `ast.unparse`.
• Triple-quoted strings used as *values* (e.g., assigned to variables) are
  preserved. Only leading docstrings of module/class/function are removed.
"""

from __future__ import annotations

import ast
from typing import Optional


def _strip_head(body: list[ast.stmt], need_stub: bool) -> list[ast.stmt]:
    """Drop a leading string literal (docstring) from a statement list.

    If `need_stub` is True and the resulting body becomes empty, a single
    `ast.Pass()` is inserted to keep the construct syntactically valid.
    """
    if body and isinstance(body[0], ast.Expr):
        v = body[0].value
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            body = body[1:]
    if need_stub and not body:
        return [ast.Pass()]
    return body


class _DocStrip(ast.NodeTransformer):
    """AST transformer that removes leading docstrings in module/class/func."""

    def visit_Module(self, node: ast.Module) -> ast.AST:  # type: ignore[override]
        self.generic_visit(node)
        node.body = _strip_head(node.body, need_stub=False)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:  # type: ignore[override]
        self.generic_visit(node)
        node.body = _strip_head(node.body, need_stub=True)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST:  # type: ignore[override]
        self.generic_visit(node)
        node.body = _strip_head(node.body, need_stub=True)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:  # type: ignore[override]
        self.generic_visit(node)
        node.body = _strip_head(node.body, need_stub=True)
        return node


def strip_comments_and_docstrings(
    source: str,
    *,
    language: Optional[str] = "py",
    filename: Optional[str] = None,
) -> str:
    """Return *source* with comments removed and, for Python, docstrings removed.

    Python strategy (default):
      • Parse to AST → remove leading string constants (module/class/function docstrings).
      • Ensure classes/functions keep a non-empty body (insert `pass` if needed).
      • Unparse back to source with `ast.unparse` (drops all `#` comments by design).

    Parameters
    ----------
    source : str
        Original Python code.
    language : Optional[str]
        Language hint; "py"/"python" triggers Python AST path (default).
    filename : Optional[str]
        Unused here; kept for API symmetry.

    Returns
    -------
    str
        Code with comments and Python docstrings removed.

    Notes
    -----
    • If parsing fails (snippet not a full module), the original source is returned.
    """
    lang = (language or "py").lower()
    if lang in {"py", "python"}:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return source  # keep original when snippet is not a full module

        tree = _DocStrip().visit(tree)  # type: ignore[arg-type]
        ast.fix_missing_locations(tree)

        try:
            # ast.unparse naturally removes '#'-style comments
            return ast.unparse(tree)  # type: ignore[attr-defined]
        except Exception:
            return source

    # Non-Python languages are out of scope here.
    return source