"""
PostgresCompiler: Postgres-specific expression compilation.

Overrides LIKE/ILIKE rendering to cast non-text operands to ``::text``
before comparison, since Postgres has no implicit integer→text coercion
for the ``~~`` (LIKE) operator.
"""

from __future__ import annotations

from .. import ast
from ..backends.postgres import Postgres
from . import compilers
from .sql import SQLCompiler

_TEXT_TYPES = frozenset(("string", "text", "json", "jsonb"))


@compilers.register_for(Postgres)
class PostgresCompiler(SQLCompiler):
    def _render_like_left(self, l: ast.Node, lowered_left: bool) -> str:
        # For non-text fields (e.g. integer) Postgres rejects bare LIKE;
        # cast the operand to text first.
        rendered = self.visit(l)
        if getattr(l, "type", None) not in _TEXT_TYPES:
            rendered = "%s::text" % rendered
        return ("LOWER(%s)" % rendered) if lowered_left else rendered


__all__ = ["PostgresCompiler"]
