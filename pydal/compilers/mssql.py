"""
MSSQLCompiler: MSSQL-specific SELECT pagination.

MSSQL does not support ANSI ``LIMIT``/``OFFSET``; it uses ``TOP`` and
(in newer versions) ``OFFSET ... ROWS FETCH NEXT ... ROWS ONLY``.

Three compilers mirror the three MSSQL dialect tiers:

MSSQLCompiler  (MSSQL, MSSQLN — "mssql", "mssql2", "mssqln")
    Emits ``SELECT TOP N ...`` for all limitby shapes.  For lmin>0 the
    ``TOP N`` still fetches up to N rows; the adapter's ``Slicer`` mixin
    then drops the first ``lmin`` rows in Python (same behaviour as the
    legacy ``MSSQLDialect.select``).

MSSQL3Compiler  (MSSQL3, MSSQL3N — "mssql3", "mssql3n")
    ``SELECT TOP N`` when lmin=0; raises ``NotImplementedError`` for
    lmin>0 so the legacy ``ROW_NUMBER()`` subquery path fires instead.

MSSQL4Compiler  (MSSQL4, MSSQL4N — "mssql4", "mssql4n")
    ``SELECT TOP N`` when lmin=0;
    ``OFFSET lmin ROWS FETCH NEXT N ROWS ONLY`` when lmin>0.
"""

from __future__ import annotations

from ..backends.mssql import MSSQL, MSSQL3, MSSQL3N, MSSQL4, MSSQL4N
from . import compilers
from .sql import SQLCompiler


@compilers.register_for(MSSQL)
class MSSQLCompiler(SQLCompiler):
    """Base MSSQL compiler: replaces ANSI LIMIT with ``SELECT TOP N``."""

    # MSSQL has no boolean literal; a bare ``0``/``1`` is rejected in a
    # condition context, so booleans must render as real comparisons.
    true_exp = "1=1"
    false_exp = "1=0"
    true_token = "1"
    false_token = "0"

    def _emit_limitby(self, n, dst):
        if not n.limit:
            return dst, "", ""
        _lmin, lmax = n.limit
        # TOP goes inside the SELECT … clause, appended to dst
        # (which may already contain " DISTINCT").
        return dst + " TOP %i" % lmax, "", ""

    # MSSQL has no EXTRACT/LENGTH; mirror the legacy MSSQLDialect.
    def fn_extract(self, args, opts):
        """Render ``DATEPART(<unit>, arg)`` — MSSQL has no ``EXTRACT``."""
        return "DATEPART(%s,%s)" % (opts.get("unit", ""), self.visit(args[0]))

    def un_epoch(self, x, _):
        """Render epoch via ``DATEDIFF(second, '1970-01-01 00:00:00', ...)``."""
        return "DATEDIFF(second, '1970-01-01 00:00:00', %s)" % self.visit(x)

    def un_length(self, x, _):
        """Render ``LEN(operand)`` — MSSQL spells ``LENGTH`` as ``LEN``."""
        return "LEN(%s)" % self.visit(x)

    def fn_aggregate(self, args, opts):
        """Render ``KIND(arg)``, mapping ``LENGTH`` to MSSQL's ``LEN``."""
        kind = opts.get("kind", "")
        if kind == "LENGTH":
            kind = "LEN"
        return "%s(%s)" % (kind, self.visit(args[0]))

    def op_add(self, l, r, opts):
        """String concatenation uses ``+`` in MSSQL (numeric stays ``+``)."""
        return "(%s + %s)" % (self.visit(l), self.visit(r))

    def fn_cast(self, args, _):
        """MSSQL needs no explicit cast — emit the operand unchanged."""
        return self.visit(args[0])

    def fn_substring(self, args, _):
        """Render ``SUBSTRING(field, pos, length)`` (MSSQL spelling)."""
        return "SUBSTRING(%s,%s,%s)" % (
            self.visit(args[0]),
            self.visit(args[1]),
            self.visit(args[2]),
        )

    def _render_like_right(self, r, lowered_left, escape_to_double):
        """Restore the uppercase national-string prefix that ILIKE
        lowercasing corrupts: MSSQLN represents strings as ``N'...'`` but
        ILIKE lowercases the whole literal to ``n'...'``, which T-SQL
        rejects. No-op for non-N MSSQL (literals start with ``'``)."""
        rendered = super()._render_like_right(r, lowered_left, escape_to_double)
        if rendered.startswith("n'"):
            return "N" + rendered[1:]
        return rendered

    def _render_update(self, n, table, sets, whr):
        """MSSQL aliased UPDATE names the alias in the leading clause and
        the full ref in a trailing FROM: ``UPDATE alias SET ... FROM ref``."""
        return "UPDATE %s SET %s FROM %s%s;" % (
            n.sqlshortref or table, sets, table, whr,
        )

    def _render_delete(self, n, table, whr):
        """MSSQL aliased DELETE: ``DELETE alias FROM ref WHERE ...``."""
        return "DELETE %s FROM %s%s;" % (n.sqlshortref or table, table, whr)


@compilers.register_for(MSSQL3)
@compilers.register_for(MSSQL3N)
class MSSQL3Compiler(MSSQLCompiler):
    """
    MSSQL3: TOP for lmin=0; falls back to the legacy ROW_NUMBER() path
    for lmin>0 (``NotImplementedError`` triggers the fallback in
    ``_ast_select_wcols``).
    """

    def _emit_limitby(self, n, dst):
        if not n.limit:
            return dst, "", ""
        lmin, lmax = n.limit
        if lmin == 0:
            return dst + " TOP %i" % lmax, "", ""
        raise NotImplementedError("MSSQL3 offset pagination uses ROW_NUMBER()")


@compilers.register_for(MSSQL4)
@compilers.register_for(MSSQL4N)
class MSSQL4Compiler(MSSQL3Compiler):
    """
    MSSQL4: TOP for lmin=0; ``OFFSET … FETCH NEXT`` for lmin>0.
    """

    def _emit_limitby(self, n, dst):
        if not n.limit:
            return dst, "", ""
        lmin, lmax = n.limit
        if lmin == 0:
            return dst + " TOP %i" % lmax, "", ""
        # offset goes after ORDER BY; limit slot stays empty
        offset = " OFFSET %i ROWS FETCH NEXT %i ROWS ONLY" % (lmin, lmax - lmin)
        return dst, "", offset


__all__ = ["MSSQLCompiler", "MSSQL3Compiler", "MSSQL4Compiler"]
