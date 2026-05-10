"""argparse-driven CLI. Pure presentation: argument parsing + exit codes.

All wiring lives in `composition/builder.py`; all business logic lives
in the use cases. This file is a translator between argv/stdout and the
application façade.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from itsm_agent.application.dto import RcaResponse
from itsm_agent.composition.builder import AgentApplication, build_default_application
from itsm_agent.composition.config import AgentConfig


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


def _report_response(response: RcaResponse) -> int:
    if response.succeeded:
        print(f"[{response.ticket_id}] report → {response.report_path}")
        return 0
    print(f"[{response.ticket_id}] FAILED: {response.error}", file=sys.stderr)
    return 1


async def _run(args: argparse.Namespace, app: AgentApplication) -> int:
    if args.ticket_id:
        return _report_response(await app.run_for_ticket(args.ticket_id))

    if args.all:
        responses = await app.run_all()
        if not responses:
            print("No open tickets returned by the repository.", file=sys.stderr)
            return 1
        rc = 0
        for r in responses:
            rc |= _report_response(r)
        return rc

    print("Provide a ticket id or --all", file=sys.stderr)
    return 2


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="itsm-agent",
        description="ITSM RCA agent (DDD / n-tier).",
    )
    p.add_argument("ticket_id", nargs="?", help="Ticket ID to process, e.g. INC-1001")
    p.add_argument("--all", action="store_true", help="Process all open tickets")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    config = AgentConfig.from_env()
    _setup_logging(config.log_level)
    args = _parse_args(argv)
    app = build_default_application(config)
    return asyncio.run(_run(args, app))


if __name__ == "__main__":
    sys.exit(main())
