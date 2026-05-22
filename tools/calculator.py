"""
title: Calculator
author: agent-stack
version: 0.1.0
description: Evalúa expresiones aritméticas seguras (sin acceso al sistema).
required_open_webui_version: 0.5.0
"""

import ast
import operator
from pydantic import BaseModel, Field


_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("expresión no permitida")


class Tools:
    class Valves(BaseModel):
        max_length: int = Field(default=200, description="Longitud máxima de la expresión")

    def __init__(self):
        self.valves = self.Valves()

    def calculate(self, expression: str) -> str:
        """
        Evalúa una expresión aritmética. Soporta + - * / // % ** y paréntesis.

        :param expression: expresión matemática, p.ej. "(3+4)*2**3"
        :return: resultado como string, o mensaje de error
        """
        if len(expression) > self.valves.max_length:
            return "error: expresión demasiado larga"
        try:
            tree = ast.parse(expression, mode="eval")
            return str(_safe_eval(tree.body))
        except Exception as e:
            return f"error: {e}"
