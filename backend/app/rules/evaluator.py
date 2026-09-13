"""Safe expression evaluator for rule packs.

Rule expressions come from YAML files that a labour-law author edits. They must
be expressive enough to state a statutory test, and completely unable to reach
the host process. ``eval()`` is not an option: a rule pack is data, and data must
never become code execution.

Approach: parse to a Python AST, then walk it against an allow-list of node
types. Anything not explicitly permitted is rejected at load time, not at
evaluation time, so a malformed rule fails in CI rather than mid-inspection.

Blocked by construction:
  * attribute access on arbitrary objects (``().__class__.__bases__``)
  * imports, lambdas, comprehensions with side effects, walrus assignment
  * calls to anything outside the function allow-list
  * dunder names anywhere in the expression
"""

from __future__ import annotations

import ast
import logging
import operator
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

logger = logging.getLogger(__name__)


class RuleSyntaxError(Exception):
    """Expression is not valid or uses a forbidden construct."""


class RuleEvaluationError(Exception):
    """Expression was valid but could not be evaluated against the facts."""


# AST nodes a rule expression may contain. Deliberately narrow.
_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.Call, ast.Name, ast.Load, ast.Constant,
    ast.List, ast.Tuple, ast.Set, ast.Dict,
    ast.Subscript, ast.Index, ast.Slice,
    ast.IfExp,
    ast.Attribute,  # permitted, but restricted to whitelisted roots (see below)
    ast.keyword,
)

_BIN_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_COMPARE_OPS: dict[type[ast.cmpop], Callable[[Any, Any], Any]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}

# Expression depth ceiling. Guards against a pathological nested expression
# exhausting the Python stack during recursive evaluation.
_MAX_DEPTH = 60


def _reject_dunder(name: str) -> None:
    if name.startswith("__") or "__" in name:
        raise RuleSyntaxError(
            f"name {name!r} is not permitted: dunder access is blocked"
        )


class ExpressionValidator(ast.NodeVisitor):
    """Rejects forbidden constructs before an expression is ever evaluated."""

    def __init__(self, allowed_functions: Iterable[str], allowed_roots: Iterable[str]):
        self._functions = set(allowed_functions)
        self._roots = set(allowed_roots)

    def visit(self, node: ast.AST) -> Any:
        if not isinstance(node, _ALLOWED_NODES):
            raise RuleSyntaxError(
                f"{type(node).__name__} is not allowed in a rule expression"
            )
        return super().visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802
        _reject_dunder(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        _reject_dunder(node.attr)

        # Walk to the root of the attribute chain. Only whitelisted fact
        # namespaces may be traversed, which stops `something.__class__` style
        # escapes even though Attribute nodes are allowed.
        root: ast.AST = node
        while isinstance(root, ast.Attribute | ast.Subscript):
            root = root.value if isinstance(root, ast.Attribute) else root.value

        if not isinstance(root, ast.Name):
            raise RuleSyntaxError(
                "attribute access is only permitted on fact namespaces"
            )
        if root.id not in self._roots:
            raise RuleSyntaxError(
                f"attribute access on {root.id!r} is not permitted; "
                f"allowed namespaces: {sorted(self._roots)}"
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if not isinstance(node.func, ast.Name):
            raise RuleSyntaxError(
                "only direct calls to allow-listed helper functions are permitted"
            )
        if node.func.id not in self._functions:
            raise RuleSyntaxError(
                f"function {node.func.id!r} is not available; "
                f"allowed: {sorted(self._functions)}"
            )
        self.generic_visit(node)


class Evaluator:
    """Compiles and evaluates rule expressions against a fact namespace."""

    def __init__(
        self,
        functions: Mapping[str, Callable[..., Any]],
        fact_roots: Sequence[str],
    ) -> None:
        self._functions = dict(functions)
        self._roots = list(fact_roots)
        self._validator = ExpressionValidator(self._functions, self._roots)
        self._cache: dict[str, ast.Expression] = {}

    # ------------------------------------------------------------------ compile
    def compile(self, expression: str) -> ast.Expression:
        """Parse and validate. Raises ``RuleSyntaxError`` on anything unsafe."""
        if expression in self._cache:
            return self._cache[expression]

        try:
            tree = ast.parse(expression.strip(), mode="eval")
        except SyntaxError as exc:
            raise RuleSyntaxError(f"invalid expression syntax: {exc.msg}") from exc

        self._validator.visit(tree)
        self._cache[expression] = tree
        return tree

    # ----------------------------------------------------------------- evaluate
    def evaluate(self, expression: str, facts: Mapping[str, Any]) -> Any:
        tree = self.compile(expression)
        try:
            return self._eval(tree.body, facts, depth=0)
        except RuleEvaluationError:
            raise
        except ZeroDivisionError:
            # Common in real data: a wage register row with zero days worked.
            # Returning None rather than raising lets a rule treat it as
            # "not determinable" instead of crashing the whole evaluation.
            return None
        except Exception as exc:
            raise RuleEvaluationError(
                f"could not evaluate {expression!r}: {type(exc).__name__}: {exc}"
            ) from exc

    def evaluate_bool(self, expression: str, facts: Mapping[str, Any]) -> bool:
        """Evaluate to a strict pass/fail.

        None is treated as False. A rule whose inputs are missing has not been
        satisfied, and must not be reported as compliant — the applicability
        check is where "does not apply" belongs.
        """
        result = self.evaluate(expression, facts)
        return bool(result) if result is not None else False

    # ----------------------------------------------------------------- internals
    def _eval(self, node: ast.AST, facts: Mapping[str, Any], *, depth: int) -> Any:
        if depth > _MAX_DEPTH:
            raise RuleEvaluationError("expression nesting is too deep")
        step = depth + 1

        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            if node.id in facts:
                return facts[node.id]
            if node.id in self._functions:
                return self._functions[node.id]
            raise RuleEvaluationError(f"unknown name {node.id!r}")

        if isinstance(node, ast.Attribute):
            target = self._eval(node.value, facts, depth=step)
            if target is None:
                # Chained access on a missing fact yields None rather than
                # raising, so `estab.registration.valid_to` is safe when there is
                # no registration.
                return None
            if isinstance(target, Mapping):
                return target.get(node.attr)
            return getattr(target, node.attr, None)

        if isinstance(node, ast.Subscript):
            target = self._eval(node.value, facts, depth=step)
            if target is None:
                return None
            key = self._eval(node.slice, facts, depth=step)
            try:
                return target[key]
            except (KeyError, IndexError, TypeError):
                return None

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for value in node.values:
                    if not self._truthy(self._eval(value, facts, depth=step)):
                        return False
                return True
            for value in node.values:
                if self._truthy(self._eval(value, facts, depth=step)):
                    return True
            return False

        if isinstance(node, ast.UnaryOp):
            operand = self._eval(node.operand, facts, depth=step)
            if isinstance(node.op, ast.Not):
                return not self._truthy(operand)
            if operand is None:
                return None
            if isinstance(node.op, ast.USub):
                return -operand
            return +operand

        if isinstance(node, ast.BinOp):
            left = self._eval(node.left, facts, depth=step)
            right = self._eval(node.right, facts, depth=step)
            if left is None or right is None:
                # Arithmetic on a missing value is not zero. Propagating None
                # keeps "unknown" distinct from "zero", which matters when the
                # result decides whether a worker was underpaid.
                return None
            handler = _BIN_OPS.get(type(node.op))
            if handler is None:
                raise RuleEvaluationError(f"operator {type(node.op).__name__} blocked")
            return handler(left, right)

        if isinstance(node, ast.Compare):
            left = self._eval(node.left, facts, depth=step)
            for op, comparator in zip(node.ops, node.comparators, strict=True):
                right = self._eval(comparator, facts, depth=step)
                handler = _COMPARE_OPS.get(type(op))
                if handler is None:
                    raise RuleEvaluationError(
                        f"comparison {type(op).__name__} blocked"
                    )
                if isinstance(op, ast.Is | ast.IsNot | ast.In | ast.NotIn):
                    if not handler(left, right):
                        return False
                else:
                    if left is None or right is None:
                        # An unknown value cannot be compared. False here would
                        # read as "the test failed", i.e. a violation, which
                        # would generate findings from missing data.
                        return None
                    if not handler(left, right):
                        return False
                left = right
            return True

        if isinstance(node, ast.IfExp):
            condition = self._eval(node.test, facts, depth=step)
            branch = node.body if self._truthy(condition) else node.orelse
            return self._eval(branch, facts, depth=step)

        if isinstance(node, ast.Call):
            assert isinstance(node.func, ast.Name)  # guaranteed by the validator
            func = self._functions[node.func.id]
            args = [self._eval(a, facts, depth=step) for a in node.args]
            kwargs = {
                kw.arg: self._eval(kw.value, facts, depth=step)
                for kw in node.keywords
                if kw.arg is not None
            }
            return func(*args, **kwargs)

        if isinstance(node, ast.List | ast.Tuple | ast.Set):
            values = [self._eval(e, facts, depth=step) for e in node.elts]
            if isinstance(node, ast.List):
                return values
            if isinstance(node, ast.Tuple):
                return tuple(values)
            return set(values)

        if isinstance(node, ast.Dict):
            return {
                self._eval(k, facts, depth=step): self._eval(v, facts, depth=step)
                for k, v in zip(node.keys, node.values, strict=True)
                if k is not None
            }

        raise RuleEvaluationError(f"cannot evaluate {type(node).__name__}")

    @staticmethod
    def _truthy(value: Any) -> bool:
        return bool(value) if value is not None else False
