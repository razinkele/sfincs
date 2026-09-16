# meteo-lt MCP server

Lithuanian weather and hydrology from [api.meteo.lt](https://api.meteo.lt/), the open
API of the Lithuanian Hydrometeorological Service (LHMT).

Registered in `~/.claude.json` as `meteo-lt`, pointing at this directory. Runs as a local stdio server through
`uv run --script`, which resolves its dependencies from the PEP 723 header in
`server.py` — it never touches the `hydromt-sfincs` micromamba environment.

    uv run --quiet --script ~/sfincs/mcp/meteo-lt/server.py   # what Claude Code runs
    uv run --with "fastmcp>=4.0,<5" --with httpx --with pytest python -m pytest test_server.py -q

## Tools

| tool | what it does |
|---|---|
| `list_places` | forecast locations, filterable by name |
| `get_forecast` | forecast for a place |
| `list_stations` | meteorological stations (AMS) |
| `get_observations` | hourly met observations, one station and date |
| `list_hydro_stations` | hydrological stations (VMS), filterable by name and water body |
| `get_data_range` | a hydro station's actual coverage — **call before a range fetch** |
| `get_hydro_observations` | hydro observations, one station and date/month |
| `fetch_hydro_range` | a date range, paged and throttled, written to CSV |

## Coverage, which is uneven

- forecasts: current only
- meteorological observations: last 10 years, hourly
- hydro `measured`: last 30 days, **hourly** (`waterLevel`, `waterTemperature`)
- hydro `historical`: since 2000, **daily** (`waterLevel`, `waterDischarge`)

Per-station coverage varies a lot and some stations have none. Measured on
2026-09-15: `smalininku-vms` and `rusnes-atmata-vms` 2000–2024, `klaipedos-vms`
(Akmena-Danė) 2008–2024, `silutes-vms` 2006–2017, `uostadvario-vms` 2020-07–2024,
while `klaipedos-juru-uosto-vms` (the Baltic seaport gauge) and `juodkrantes-vms`
(Curonian Lagoon) return a null range — no historical data at all.

**There is no hourly pre-2000s-era series here.** `historical` is daily, and
`measured` only reaches back 30 days, so this API cannot supply an hourly 2013 sea
boundary for the Curonian SFINCS model.

## Rate limits

180 requests/minute and 20,000/day per IP; LHMT states that exceeding the daily
ceiling can get an IP blocked without notice. `RATE_LIMIT_PER_MINUTE` is set to 60,
a third of the allowance, and `fetch_hydro_range` throttles through it.

## Licence

Data © Lithuanian Hydrometeorological Service, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
Attribution is a condition of access, so every tool response carries the notice.
