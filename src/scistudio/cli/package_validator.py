"""CLI wrapper for the ADR-049 package validator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from scistudio.packages.validation import PackageValidationProfile, validate_package
from scistudio.packages.validation.models import PackageValidationStatus


def _typer_command(
    candidate: Annotated[
        str,
        typer.Argument(help="Source tree path, archive, or installed distribution name"),
    ],
    profile: Annotated[
        PackageValidationProfile,
        typer.Option("--profile", case_sensitive=False, help="Validation profile."),
    ] = PackageValidationProfile.DEVELOPMENT,
    as_json: Annotated[bool, typer.Option("--json", help="Emit the structured report as JSON.")] = False,
) -> None:
    """Validate one SciStudio extension package."""

    target: str | Path = Path(candidate) if Path(candidate).exists() else candidate
    report = validate_package(target, profile=profile)
    payload = report.to_dict()
    if as_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True))
    else:
        typer.echo(f"{payload['package']['name']} {payload['status']} ({payload['registration_decision']})")
        for finding in payload["findings"]:
            typer.echo(
                f"- {finding['severity']} {finding['contract_id']} "
                f"{finding.get('symbol', finding['surface'])}: {finding['message']}"
            )
    if report.status == PackageValidationStatus.FAIL:
        raise typer.Exit(code=1)


def register(app: typer.Typer) -> None:
    """Register the ``package-validator`` subcommand on the root CLI."""

    app.command("package-validator")(_typer_command)


if __name__ == "__main__":
    typer.run(_typer_command)
