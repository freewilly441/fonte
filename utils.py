import ast
import math
from datetime import date, timedelta


def safe_calc(expr: str) -> str:
    expr = expr.strip()
    if not expr:
        return ""
    try:
        node = ast.parse(expr, mode="eval")
        for n in ast.walk(node):
            if not isinstance(
                n,
                (
                    ast.Expression,
                    ast.BinOp,
                    ast.UnaryOp,
                    ast.Num,
                    ast.Constant,
                    ast.Add,
                    ast.Sub,
                    ast.Mult,
                    ast.Div,
                    ast.Mod,
                    ast.Pow,
                    ast.USub,
                    ast.UAdd,
                    ast.Load,
                    ast.Name,
                    ast.Call,
                ),
            ):
                raise ValueError("Unsupported expression")
            if isinstance(n, ast.Name) and n.id not in {"pi", "e"}:
                raise ValueError("Unsupported name")
            if isinstance(n, ast.Call):
                if not isinstance(n.func, ast.Name) or n.func.id not in {
                    "sin",
                    "cos",
                    "tan",
                    "sqrt",
                    "log",
                }:
                    raise ValueError("Unsupported function")
        value = eval(
            compile(node, "<calc>", "eval"),
            {"__builtins__": {}},
            {
                "pi": math.pi,
                "e": math.e,
                "sin": math.sin,
                "cos": math.cos,
                "tan": math.tan,
                "sqrt": math.sqrt,
                "log": math.log,
            },
        )
        return str(value)
    except Exception as exc:
        return f"Error: {exc}"


LENGTH_UNITS = {
    "m": 1.0,
    "km": 1000.0,
    "cm": 0.01,
    "mm": 0.001,
    "inch": 0.0254,
    "ft": 0.3048,
    "yd": 0.9144,
    "mile": 1609.34,
}

MASS_UNITS = {
    "kg": 1.0,
    "g": 0.001,
    "mg": 0.000001,
    "lb": 0.453592,
    "oz": 0.0283495,
}


def convert_length(value: float, from_unit: str, to_unit: str) -> float:
    return value * LENGTH_UNITS[from_unit] / LENGTH_UNITS[to_unit]


def convert_mass(value: float, from_unit: str, to_unit: str) -> float:
    return value * MASS_UNITS[from_unit] / MASS_UNITS[to_unit]


def convert_temp(value: float, from_unit: str, to_unit: str) -> float:
    if from_unit == to_unit:
        return value
    if from_unit == "C":
        c = value
    elif from_unit == "F":
        c = (value - 32) * 5 / 9
    elif from_unit == "K":
        c = value - 273.15
    else:
        raise ValueError("Unknown unit")
    if to_unit == "C":
        return c
    if to_unit == "F":
        return c * 9 / 5 + 32
    if to_unit == "K":
        return c + 273.15
    raise ValueError("Unknown unit")


def date_add_days(iso_date: str, days: int) -> str:
    d = date.fromisoformat(iso_date)
    return (d + timedelta(days=days)).isoformat()


def today_iso() -> str:
    return date.today().isoformat()
