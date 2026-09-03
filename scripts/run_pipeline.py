#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_ARCHIVE_ROOT = Path("/home/WRF-operational-archive")
INIT_HOUR = 3


def parse_date(value: str) -> datetime:

    if len(value) != 8 or not value.isdigit():
        raise argparse.ArgumentTypeError(
            f"niepoprawna data {value!r}; oczekiwano YYYYMMDD"
        )

    try:
        return datetime.strptime(value, "%Y%m%d") + timedelta(hours=INIT_HOUR)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"niepoprawna data {value!r}; oczekiwano YYYYMMDD"
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--date",
        required=True,
        type=parse_date,
        metavar="YYYYMMDD",
        help="data inicjalizacji biegu WRF",
    )
    parser.add_argument(
        "--wrfout",
        type=Path,
        help="jawna ścieżka wejściowa; pomija wyszukiwanie w archiwum",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    return parser.parse_args()


def find_wrfout(archive_root: Path, run_date: datetime) -> Path:
    run_dir = (
        archive_root
        / run_date.strftime("%Y")
        / run_date.strftime("%m")
        / run_date.strftime("%Y%m%d")
        / "Results"
    )

    wrfout = run_dir / f"wrfout_d01_{run_date:%Y-%m-%d_%H:%M:%S}"

    if not wrfout.is_file():
        raise SystemExit(f"Nie znaleziono pliku WRFOUT: {wrfout}")

    return wrfout


def main() -> None:
    args = parse_args()
    date_text = args.date.strftime("%Y%m%d%H")

    if args.wrfout:
        wrfout = args.wrfout.expanduser().resolve()
        if not wrfout.is_file():
            raise SystemExit(f"Nie znaleziono pliku WRFOUT: {wrfout}")
    else:
        wrfout = find_wrfout(DEFAULT_ARCHIVE_ROOT, args.date)

    project_dir = Path(__file__).resolve().parent.parent
    wrfdiag = (
        project_dir / "input" / "wrfdiag" / (f"wrfdiag_d01_{args.date:%Y-%m-%d_%H}.nc")
    )
    command = [
        "make",
        "pipeline",
        f"PIPELINE_DATE_TIME={date_text}",
        f"WRFOUT={wrfout}",
        f"WRFDIAG={wrfdiag}",
    ]

    print(f"WRFOUT:  {wrfout}")
    print(f"WRFDIAG: {wrfdiag}")
    print("Polecenie:", " ".join(command))
    if not args.dry_run:
        subprocess.run(command, cwd=project_dir, check=True)


if __name__ == "__main__":
    main()
