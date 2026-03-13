"""Checkpoint and persistence layer for resumable batch runs.

Writes results incrementally to Parquet and tracks execution state so
that interrupted runs can resume without re-computing finished chunks.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger

from suitetrading.backtesting._internal.schemas import BacktestCheckpoint, RESULT_COLUMNS


class CheckpointManager:
    """Manages run checkpoints and incremental result persistence."""

    def __init__(self, output_dir: Path | str) -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._checkpoint_file = self._dir / "checkpoints.json"
        self._checkpoints: dict[str, BacktestCheckpoint] = {}
        self._load_existing()

    # ── Checkpoint state ──────────────────────────────────────────────

    def is_chunk_done(self, chunk_id: int) -> bool:
        key = str(chunk_id)
        cp = self._checkpoints.get(key)
        return cp is not None and cp.status == "done"

    def mark_running(self, chunk_id: int) -> None:
        self._checkpoints[str(chunk_id)] = BacktestCheckpoint(
            run_id="",
            chunk_id=chunk_id,
            status="running",
            started_at=_now_iso(),
        )
        self._persist_checkpoints()

    def mark_done(self, chunk_id: int, output_path: str) -> None:
        key = str(chunk_id)
        cp = self._checkpoints.get(key)
        if cp:
            cp.status = "done"
            cp.finished_at = _now_iso()
            cp.output_path = output_path
        else:
            self._checkpoints[key] = BacktestCheckpoint(
                run_id="",
                chunk_id=chunk_id,
                status="done",
                started_at=_now_iso(),
                finished_at=_now_iso(),
                output_path=output_path,
            )
        self._persist_checkpoints()

    def mark_error(self, chunk_id: int, error: str) -> None:
        key = str(chunk_id)
        cp = self._checkpoints.get(key)
        if cp:
            cp.status = "error"
            cp.finished_at = _now_iso()
            cp.error = error
        else:
            self._checkpoints[key] = BacktestCheckpoint(
                run_id="",
                chunk_id=chunk_id,
                status="error",
                started_at=_now_iso(),
                finished_at=_now_iso(),
                error=error,
            )
        self._persist_checkpoints()

    def completed_count(self) -> int:
        return sum(1 for cp in self._checkpoints.values() if cp.status == "done")

    def total_count(self) -> int:
        return len(self._checkpoints)

    # ── Result persistence ────────────────────────────────────────────

    def save_chunk_results(
        self,
        chunk_id: int,
        results: list[dict[str, Any]],
    ) -> str:
        """Write results for one chunk to Parquet.  Returns output path."""
        rows: list[dict[str, Any]] = []
        for r in results:
            row: dict[str, Any] = {}
            for col in RESULT_COLUMNS:
                row[col] = r.get(col)
            rows.append(row)

        df = pd.DataFrame(rows, columns=RESULT_COLUMNS)
        path = self._dir / f"chunk_{chunk_id:06d}.parquet"
        df.to_parquet(path, engine="pyarrow", compression="zstd", index=False)
        logger.debug("Saved chunk {} → {}", chunk_id, path)
        return str(path)

    def load_all_results(self) -> pd.DataFrame:
        """Load and concatenate all completed chunk Parquets."""
        parts = sorted(self._dir.glob("chunk_*.parquet"))
        if not parts:
            return pd.DataFrame(columns=RESULT_COLUMNS)
        dfs = [pd.read_parquet(p) for p in parts]
        return pd.concat(dfs, ignore_index=True)

    # ── Internal ──────────────────────────────────────────────────────

    def _load_existing(self) -> None:
        if not self._checkpoint_file.exists():
            return
        data = json.loads(self._checkpoint_file.read_text())
        for key, cp_dict in data.items():
            self._checkpoints[key] = BacktestCheckpoint(**cp_dict)

    def _persist_checkpoints(self) -> None:
        data = {}
        for key, cp in self._checkpoints.items():
            data[key] = {
                "run_id": cp.run_id,
                "chunk_id": cp.chunk_id,
                "status": cp.status,
                "started_at": cp.started_at,
                "finished_at": cp.finished_at,
                "output_path": cp.output_path,
                "error": cp.error,
            }
        self._checkpoint_file.write_text(json.dumps(data, indent=2))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
