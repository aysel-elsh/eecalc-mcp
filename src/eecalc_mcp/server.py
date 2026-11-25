"""MCP server that gives AI assistants exact electronics calculations.

Language models are bad at arithmetic like IPC-2221 exponents or picking the
nearest E96 resistor. This server hands those jobs to `eecalc`, so the
assistant calls a tool and gets the exact number back.

Every numeric argument also accepts a string with an SI prefix or RKM code:
"4.7k", "4k7", "100n", "2M2", "4R7".
"""

from __future__ import annotations

import functools
from typing import Any, Literal, Union

import eecalc as ee
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

Num = Union[float, str]
Layer = Literal["external", "internal"]
Series = Literal["E3", "E6", "E12", "E24", "E48", "E96", "E192"]

mcp = MCPServer(
    name="eecalc",
    version="0.1.0",
    instructions=(
        "Exact electronics calculations. Use these tools instead of doing EE math "
        "yourself: PCB trace width (IPC-2221), standard resistor/capacitor values "
        "(E-series), voltage dividers, LED resistors, RC/LC filters, microstrip "
        "impedance and Ohm's law. Numbers may be passed as strings with SI prefixes "
        "like '4k7' or '100n'. Units are SI (ohms, farads, henries, volts, amps, Hz) "
        "except PCB dimensions, which are millimetres, and copper weight, in oz."
    ),
)

_PURE = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)


def _n(x: Num) -> float:
    try:
        return ee.parse(x)
    except ValueError as e:
        raise ToolError(str(e)) from None


def _tool(fn):
    """Register a pure calculation tool and turn ValueErrors into clean tool errors."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValueError as e:
            raise ToolError(str(e)) from None

    return mcp.tool(annotations=_PURE, structured_output=True)(wrapper)


# ---------------------------------------------------------------- PCB ------


@_tool
def pcb_trace_width(
    current_a: Num,
    temp_rise_c: Num = 10,
    copper_oz: Num = 1,
    layer: Layer = "external",
) -> dict[str, Any]:
    """Minimum PCB trace width to carry a current without exceeding a temperature rise (IPC-2221).

    Returns width in mm and mil. Internal layers need roughly 2.6x the width of external ones.
    """
    w = ee.trace_width(_n(current_a), _n(temp_rise_c), _n(copper_oz), layer)
    return {
        "width_mm": round(w.width_mm, 4),
        "width_mil": round(w.width_mil, 2),
        "cross_section_mil2": round(w.area_mil2, 2),
        "layer": w.layer,
        "standard": "IPC-2221",
    }


@_tool
def pcb_trace_current(
    width_mm: Num,
    temp_rise_c: Num = 10,
    copper_oz: Num = 1,
    layer: Layer = "external",
) -> dict[str, Any]:
    """Maximum current a PCB trace of a given width can carry for a temperature rise (IPC-2221)."""
    i = ee.trace_current(_n(width_mm), _n(temp_rise_c), _n(copper_oz), layer)
    return {"max_current_a": round(i, 4), "standard": "IPC-2221"}


@_tool
def pcb_trace_resistance(
    width_mm: Num,
    length_mm: Num,
    copper_oz: Num = 1,
    temp_c: Num = 25,
    current_a: Num | None = None,
) -> dict[str, Any]:
    """DC resistance of a copper PCB trace. If current_a is given, also returns voltage drop and power loss."""
    r = ee.trace_resistance(_n(width_mm), _n(length_mm), _n(copper_oz), _n(temp_c))
    out = {"resistance_ohm": r, "resistance": ee.fmt(r, "Ω")}
    if current_a is not None:
        i = _n(current_a)
        out |= {"voltage_drop_v": i * r, "power_loss_w": i * i * r}
    return out


@_tool
def pcb_microstrip_impedance(
    width_mm: Num,
    dielectric_height_mm: Num,
    er: Num = 4.4,
    copper_oz: Num = 1,
) -> dict[str, Any]:
    """Characteristic impedance of a surface microstrip trace (IPC-2141). FR-4 er is about 4.2-4.6.

    Accurate to a few percent for 0.1 < width/height < 2.0.
    """
    w, h = _n(width_mm), _n(dielectric_height_mm)
    z = ee.microstrip_impedance(w, h, _n(er), _n(copper_oz))
    out = {"impedance_ohm": round(z, 2), "standard": "IPC-2141"}
    if not 0.1 < w / h < 2.0:
        out["warning"] = f"w/h = {w / h:.2f} is outside 0.1-2.0; the formula loses accuracy here"
    return out


# --------------------------------------------------------- E-series ------


@_tool
def nearest_standard_value(value: Num, series: Series = "E24") -> dict[str, Any]:
    """Snap a resistor/capacitor/inductor value to the nearest standard E-series value (IEC 60063).

    E12 is common 10% parts, E24 is 5%, E96 is 1%.
    """
    v = _n(value)
    s = ee.nearest(v, series)
    return {"standard_value": s, "formatted": ee.fmt(s), "series": series, "error_pct": round((s - v) / v * 100, 3)}


@_tool
def list_standard_values(series: Series = "E24", min_value: Num = 1, max_value: Num = 10) -> dict[str, Any]:
    """List every standard E-series value in a range, e.g. all E24 values between 1k and 10k."""
    vals = ee.values(series, _n(min_value), _n(max_value))
    if len(vals) > 500:
        raise ToolError("range too large (over 500 values); narrow min_value/max_value")
    return {"series": series, "values": vals}


@_tool
def design_voltage_divider(
    vin: Num,
    vout: Num,
    series: Series = "E24",
    r_min: Num = "1k",
    r_max: Num = "100k",
) -> dict[str, Any]:
    """Pick the best pair of standard resistors for a voltage divider (Vout = Vin * Rb / (Rt + Rb))."""
    vi, vo = _n(vin), _n(vout)
    if not 0 < vo < vi:
        raise ToolError("vout must be between 0 and vin")
    p = ee.divider_pair(vo / vi, series, _n(r_min), _n(r_max))
    return {
        "r_top_ohm": p.r_top,
        "r_bottom_ohm": p.r_bottom,
        "r_top": ee.fmt(p.r_top, "Ω"),
        "r_bottom": ee.fmt(p.r_bottom, "Ω"),
        "actual_vout_v": round(vi * p.ratio, 5),
        "error_pct": round(p.error_pct, 3),
        "divider_current_a": vi / (p.r_top + p.r_bottom),
    }


# ---------------------------------------------------------- circuits ------


@_tool
def led_series_resistor(
    supply_v: Num,
    led_forward_v: Num,
    led_current_a: Num = 0.02,
    leds_in_series: int = 1,
    series: Series = "E24",
) -> dict[str, Any]:
    """Series resistor for an LED (or a string of LEDs). Rounds up to a standard value and suggests a power rating."""
    r = ee.led_resistor(_n(supply_v), _n(led_forward_v), _n(led_current_a), leds_in_series, series)
    return {
        "standard_resistor_ohm": r.standard_ohms,
        "exact_resistor_ohm": round(r.exact_ohms, 3),
        "actual_led_current_a": round(r.actual_current_a, 6),
        "resistor_power_w": round(r.resistor_power_w, 6),
        "suggested_power_rating_w": r.suggested_rating_w,
    }


@_tool
def rc_filter(r_ohm: Num | None = None, c_farad: Num | None = None, target_cutoff_hz: Num | None = None) -> dict[str, Any]:
    """First-order RC filter. Give R and C to get the cutoff frequency and time constant,
    or give target_cutoff_hz (and optionally C) to pick standard R and C values."""
    if target_cutoff_hz is not None:
        pick = ee.rc_for_cutoff(_n(target_cutoff_hz), _n(c_farad) if c_farad is not None else None)
        return {
            "r_ohm": pick.r,
            "c_farad": pick.c,
            "r": ee.fmt(pick.r, "Ω"),
            "c": ee.fmt(pick.c, "F"),
            "cutoff_hz": round(pick.cutoff_hz, 4),
            "error_pct": round(pick.error_pct, 3),
        }
    if r_ohm is None or c_farad is None:
        raise ToolError("give r_ohm and c_farad, or target_cutoff_hz")
    r, c = _n(r_ohm), _n(c_farad)
    return {"cutoff_hz": ee.rc_cutoff(r, c), "time_constant_s": ee.time_constant(r, c)}


@_tool
def lc_resonance(l_henry: Num, c_farad: Num) -> dict[str, Any]:
    """Resonant frequency of an LC circuit: f = 1 / (2π√(LC))."""
    l, c = _n(l_henry), _n(c_farad)
    f = ee.lc_resonance(l, c)
    return {"resonant_hz": f, "formatted": ee.fmt(f, "Hz"), "characteristic_impedance_ohm": (l / c) ** 0.5}


@_tool
def reactance(frequency_hz: Num, c_farad: Num | None = None, l_henry: Num | None = None) -> dict[str, Any]:
    """Reactance of a capacitor and/or inductor at a frequency, in ohms."""
    f = _n(frequency_hz)
    out = {}
    if c_farad is not None:
        out["xc_ohm"] = ee.reactance_c(f, _n(c_farad))
    if l_henry is not None:
        out["xl_ohm"] = ee.reactance_l(f, _n(l_henry))
    if not out:
        raise ToolError("give c_farad and/or l_henry")
    return out


@_tool
def combine_components(values: list[Num], how: Literal["series", "parallel"]) -> dict[str, Any]:
    """Combine resistors (or inductors) in series or parallel. For capacitors, swap: caps in parallel add."""
    nums = [_n(v) for v in values]
    total = ee.series(*nums) if how == "series" else ee.parallel(*nums)
    return {"total": total, "formatted": ee.fmt(total)}


@_tool
def ohms_law(
    voltage_v: Num | None = None,
    current_a: Num | None = None,
    resistance_ohm: Num | None = None,
) -> dict[str, Any]:
    """Ohm's law and power. Give exactly two of voltage, current, resistance; returns all four (V, I, R, P)."""
    v = _n(voltage_v) if voltage_v is not None else None
    i = _n(current_a) if current_a is not None else None
    r = _n(resistance_ohm) if resistance_ohm is not None else None
    res = ee.power(v=v, i=i, r=r)
    return {"voltage_v": res["v"], "current_a": res["i"], "resistance_ohm": res["r"], "power_w": res["p"]}


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
