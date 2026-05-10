"""
cli.py
=======

WP5.4 (P5.4) v1.0 Click-based CLI mirroring the API.

Subcommands:

* ``locate``    -- run the locator on a (V, I) phasor pair.
* ``map``       -- emit the identifiability heatmap CSV.
* ``envelope``  -- emit the CRLB envelope CSV.
* ``validate``  -- end-to-end self-check on a stored 720-cell
                   sample bundle (sanity check that the API +
                   optimiser + identifiability stack is wired up).

The CLI is a *thin* wrapper around the same handlers used by
``api.py`` -- so an integration test that targets the CLI is
equivalent to an integration test that targets the API.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import click

from .api import (
    API_VERSION,
    handle_crlb_envelope,
    handle_health,
    handle_identifiability_map,
    handle_locate,
)


@click.group(help=f"sambps-protection-validation/{API_VERSION} CLI")
@click.version_option(API_VERSION, "-V", "--version")
def cli() -> None:
    pass


@cli.command(help="Run the locator on a (V_phasor, I_phasor) pair.")
@click.option("--vre", type=float, required=True, help="Re(V_phasor) [V]")
@click.option("--vim", type=float, required=True, help="Im(V_phasor) [V]")
@click.option("--ire", type=float, required=True, help="Re(I_phasor) [A]")
@click.option("--iim", type=float, required=True, help="Im(I_phasor) [A]")
@click.option("--network-id", type=str, default="single_line_11kV_100km",
              show_default=True)
@click.option("--fault-type", type=click.Choice(["SLG", "LL", "LLG"]),
              default="SLG", show_default=True)
def locate(vre: float, vim: float, ire: float, iim: float,
           network_id: str, fault_type: str) -> None:
    out = handle_locate({
        "V_phasor": [vre, vim],
        "I_phasor": [ire, iim],
        "network_id": network_id,
        "fault_type": fault_type,
    })
    click.echo(json.dumps(out, indent=2))
    if out.get("status", 200) != 200:
        sys.exit(1)


@cli.command(help="Emit the identifiability heatmap CSV for a network.")
@click.option("--network-id", type=str, default="single_line_11kV_100km",
              show_default=True)
@click.option("--output", type=click.Path(dir_okay=False), default="-",
              show_default=True,
              help="output path; '-' = stdout")
def map(network_id: str, output: str) -> None:
    out = handle_identifiability_map(network_id)
    if out.get("status", 200) != 200:
        click.echo(json.dumps(out, indent=2), err=True)
        sys.exit(1)
    alphas = out["alphas"]
    Rxs = out["Rxs"]
    grid = out["sigma_min_grid"]
    if output == "-":
        fh = sys.stdout
        writer = csv.writer(fh)
        writer.writerow(["alpha", "Rx", "sigma_min"])
        for ia, a in enumerate(alphas):
            for ir, R in enumerate(Rxs):
                writer.writerow([a, R, grid[ia][ir]])
    else:
        with Path(output).open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["alpha", "Rx", "sigma_min"])
            for ia, a in enumerate(alphas):
                for ir, R in enumerate(Rxs):
                    writer.writerow([a, R, grid[ia][ir]])
        click.echo(f"wrote {output}")


@cli.command(help="Emit the CRLB envelope CSV for a network at a given SNR.")
@click.option("--network-id", type=str, default="single_line_11kV_100km",
              show_default=True)
@click.option("--snr", type=float, default=40.0, show_default=True,
              help="SNR_I in dB")
@click.option("--output", type=click.Path(dir_okay=False), default="-",
              show_default=True,
              help="output path; '-' = stdout")
def envelope(network_id: str, snr: float, output: str) -> None:
    out = handle_crlb_envelope(network_id, snr)
    if out.get("status", 200) != 200:
        click.echo(json.dumps(out, indent=2), err=True)
        sys.exit(1)
    alphas = out["alphas"]
    crlb_alpha = out["crlb_alpha_envelope"]
    crlb_Rx = out["crlb_Rx_envelope"]
    rows = [["alpha", "crlb_alpha", "crlb_Rx"]]
    rows.extend([[a, ca, cr] for a, ca, cr in zip(alphas, crlb_alpha, crlb_Rx, strict=False)])
    if output == "-":
        writer = csv.writer(sys.stdout)
        writer.writerows(rows)
    else:
        with Path(output).open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerows(rows)
        click.echo(f"wrote {output}")


@cli.command(help="End-to-end self-check on the registered networks.")
def validate() -> None:
    """End-to-end smoke check: hits health, identifiability_map, and
    crlb_envelope on each registered network and reports OK / FAIL."""
    health = handle_health()
    if health.get("status", 200) != 200:
        click.echo("health: FAIL", err=True)
        sys.exit(1)
    click.echo(f"health: OK (registry = {health['registry']})")
    fail = 0
    for net in health["registry"]:
        ident = handle_identifiability_map(net)
        ok = ident.get("status", 200) == 200
        click.echo(f"identifiability_map[{net}]: {'OK' if ok else 'FAIL'}")
        if not ok:
            fail += 1
        env = handle_crlb_envelope(net, 40.0)
        ok = env.get("status", 200) == 200
        click.echo(f"crlb_envelope[{net}]: {'OK' if ok else 'FAIL'}")
        if not ok:
            fail += 1
    if fail:
        click.echo(f"validate: {fail} subchecks FAILED", err=True)
        sys.exit(1)
    click.echo("validate: all subchecks OK")


def main() -> int:
    cli()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
