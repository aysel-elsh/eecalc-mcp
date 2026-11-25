import anyio
import pytest
from mcp import Client

from eecalc_mcp.server import mcp

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def call(name, args):
    async with Client(mcp) as client:
        return await client.call_tool(name, args)


async def test_lists_all_tools():
    async with Client(mcp) as client:
        tools = (await client.list_tools()).tools
    names = {t.name for t in tools}
    assert {
        "pcb_trace_width",
        "pcb_trace_current",
        "pcb_trace_resistance",
        "pcb_microstrip_impedance",
        "nearest_standard_value",
        "list_standard_values",
        "design_voltage_divider",
        "led_series_resistor",
        "rc_filter",
        "lc_resonance",
        "reactance",
        "combine_components",
        "ohms_law",
    } <= names
    # every tool documents itself and is marked read-only
    for t in tools:
        assert t.description
        assert t.annotations.read_only_hint is True


async def test_trace_width():
    r = await call("pcb_trace_width", {"current_a": 1})
    assert not r.is_error
    assert r.structured_content["width_mil"] == pytest.approx(11.83, abs=0.01)


async def test_si_strings_accepted():
    r = await call("combine_components", {"values": ["4k7", "4.7k"], "how": "parallel"})
    assert r.structured_content["total"] == pytest.approx(2350)


async def test_divider():
    r = await call("design_voltage_divider", {"vin": 5, "vout": 3.3})
    assert abs(r.structured_content["error_pct"]) < 0.5


async def test_led():
    r = await call("led_series_resistor", {"supply_v": 5, "led_forward_v": 2, "led_current_a": "20m"})
    assert r.structured_content["standard_resistor_ohm"] == 150


async def test_rc_pick():
    r = await call("rc_filter", {"target_cutoff_hz": "1k"})
    assert abs(r.structured_content["error_pct"]) < 3


async def test_ohms_law():
    r = await call("ohms_law", {"voltage_v": 12, "resistance_ohm": 6})
    assert r.structured_content["power_w"] == 24


async def test_microstrip_warns_outside_range():
    r = await call("pcb_microstrip_impedance", {"width_mm": 3, "dielectric_height_mm": 0.2})
    assert "warning" in r.structured_content


async def test_bad_input_is_a_clean_tool_error():
    r = await call("led_series_resistor", {"supply_v": 3.3, "led_forward_v": 3.2, "leds_in_series": 2})
    assert r.is_error
    assert "supply" in r.content[0].text

    r = await call("nearest_standard_value", {"value": "banana"})
    assert r.is_error
    assert "parse" in r.content[0].text
