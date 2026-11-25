# eecalc-mcp

**An MCP server that gives AI assistants exact electronics math.**

Ask Claude "how wide should a 3 A trace be on 2 oz copper?" and it will often guess at the
IPC-2221 exponents and get it wrong. With this server it calls a tool and gets the exact number.
Built on [eecalc](https://github.com/aysel-elsh/eecalc).

## Tools

| Tool | What it does |
|---|---|
| `pcb_trace_width` | Min trace width for a current and temperature rise (IPC-2221) |
| `pcb_trace_current` | Max current for a trace width (IPC-2221) |
| `pcb_trace_resistance` | DC resistance, plus voltage drop and power loss if you give a current |
| `pcb_microstrip_impedance` | Microstrip Z0 (IPC-2141), warns when outside the formula's range |
| `nearest_standard_value` | Snap to E3–E192 (IEC 60063) |
| `list_standard_values` | Every standard value in a range |
| `design_voltage_divider` | Best standard resistor pair for Vin → Vout |
| `led_series_resistor` | LED resistor, rounded up, with a power rating |
| `rc_filter` | Cutoff from R and C, or pick standard R and C for a cutoff |
| `lc_resonance` | Resonant frequency and characteristic impedance |
| `reactance` | Xc and Xl at a frequency |
| `combine_components` | Series / parallel |
| `ohms_law` | Any two of V, I, R → all of V, I, R, P |

All tools are read-only and work offline. Numbers can be sent as `"4k7"`, `"100n"`, `"2M2"`.

## Install

Needs [uv](https://docs.astral.sh/uv/) (or use `pip install git+https://github.com/aysel-elsh/eecalc-mcp`
and run `eecalc-mcp`).

**Claude Code**

```bash
claude mcp add eecalc -- uvx --from git+https://github.com/aysel-elsh/eecalc-mcp eecalc-mcp
```

**Claude Desktop**: add to `claude_desktop_config.json`

```json
{
  "mcpServers": {
    "eecalc": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/aysel-elsh/eecalc-mcp", "eecalc-mcp"]
    }
  }
}
```

**Cursor / VS Code / others**: same `command` and `args` in your MCP config.

## Try asking

- "I need to run 5 A on an inner layer of 1 oz copper with a 20 °C rise. How wide?"
- "Pick E96 resistors to divide 12 V down to 3.3 V for an ADC."
- "What resistor for three white LEDs in series on 12 V at 15 mA?"
- "Give me standard parts for a 2.5 kHz RC low-pass."

## Develop

```bash
pip install -e ".[test]" && pytest
```

New tools should wrap a tested function in eecalc. Ideas: stripline, IPC-2152, op-amp gain,
555 timer, battery life, buck converter inductor sizing.

MIT License.
