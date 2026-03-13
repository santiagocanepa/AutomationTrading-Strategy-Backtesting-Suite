"""Audit raw parquet partitions and optionally quarantine invalid files.

Usage::

    python scripts/audit_raw_data.py
    python scripts/audit_raw_data.py --apply
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))


VALID_YEAR_MIN = 2000
VALID_YEAR_MAX = 2100


@dataclass(slots=True)
class InvalidPartition:
    path: Path
    reason: str
    date_min: str | None
    date_max: str | None


def _extract_year(value: str | None) -> int | None:
    if not value:
        return None
    head = value.split("-", 1)[0]
    if head.lstrip("-").isdigit():
        return int(head)
    return None


def _is_valid_year(year: int | None) -> bool:
    return year is not None and VALID_YEAR_MIN <= year <= VALID_YEAR_MAX


def audit_store(raw_dir: Path) -> list[InvalidPartition]:
    invalid: list[InvalidPartition] = []
    for fp in sorted(raw_dir.glob("**/*.parquet")):
        meta = pq.read_metadata(fp)
        custom = meta.metadata or {}
        date_min_raw = custom.get(b"date_min")
        date_max_raw = custom.get(b"date_max")
        date_min = date_min_raw.decode() if date_min_raw else None
        date_max = date_max_raw.decode() if date_max_raw else None

        stem_year = _extract_year(fp.stem)
        min_year = _extract_year(date_min)
        max_year = _extract_year(date_max)

        reason: str | None = None
        if not _is_valid_year(stem_year):
            reason = f"invalid filename year: {stem_year}"
        elif not _is_valid_year(min_year) or not _is_valid_year(max_year):
            reason = f"invalid metadata year: {min_year} → {max_year}"
        elif stem_year != min_year:
            reason = f"filename/metadata mismatch: stem={stem_year}, date_min={min_year}"

        if reason is not None:
            invalid.append(InvalidPartition(fp, reason, date_min, date_max))
    return invalid


def quarantine_partitions(invalid: list[InvalidPartition], raw_dir: Path, quarantine_dir: Path) -> int:
    moved = 0
    for item in invalid:
        relative = item.path.relative_to(raw_dir)
        target = quarantine_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(item.path), str(target))
        moved += 1
    return moved


def write_report(invalid: list[InvalidPartition], output_path: Path, raw_dir: Path, applied: bool) -> None:
    grouped: dict[str, int] = defaultdict(int)
    for item in invalid:
        parts = item.path.relative_to(raw_dir).parts
        key = "/".join(parts[:3]) if len(parts) >= 3 else str(item.path)
        grouped[key] += 1

    lines = [
        "# Raw Data Integrity Report",
        "",
        f"Invalid partitions found: {len(invalid)}",
        f"Quarantine applied: {'yes' if applied else 'no'}",
        "",
        "## Summary by dataset",
        "",
        "| Dataset | Invalid files |",
        "|---------|---------------:|",
    ]
    for dataset, count in sorted(grouped.items()):
        lines.append(f"| {dataset} | {count} |")

    lines.extend([
        "",
        "## Sample invalid partitions",
        "",
        "| File | Reason | date_min | date_max |",
        "|------|--------|----------|----------|",
    ])
    for item in invalid[:20]:
        rel = item.path.relative_to(raw_dir)
        lines.append(f"| {rel} | {item.reason} | {item.date_min or ''} | {item.date_max or ''} |")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit raw parquet partitions and quarantine invalid ones")
    parser.add_argument("--raw-dir", default="data/raw")
    parser.add_argument("--quarantine-dir", default="data/quarantine")
    parser.add_argument("--report", default="docs/raw_data_integrity_report.md")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    raw_dir = PROJECT_ROOT / args.raw_dir
    quarantine_dir = PROJECT_ROOT / args.quarantine_dir
    report_path = PROJECT_ROOT / args.report

    invalid = audit_store(raw_dir)
    moved = 0
    if args.apply and invalid:
        moved = quarantine_partitions(invalid, raw_dir, quarantine_dir)

    write_report(invalid, report_path, raw_dir, applied=args.apply)
    print(f"Invalid partitions: {len(invalid)}")
    if args.apply:
        print(f"Quarantined: {moved}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()