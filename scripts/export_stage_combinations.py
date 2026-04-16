"""Export seg1 + segN video combinations from a segmented Quest dataset.

Usage:
    python ./scripts/export_stage_combinations.py --name demo
    python ./scripts/export_stage_combinations.py --name demo --no-include-aligned
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from copy import deepcopy
from pathlib import Path

import imageio.v2 as imageio
import pyarrow as pa
import pyarrow.parquet as pq


DEFAULT_OUTPUT_ROOT = "./data"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_stage_combinations",
        description="Export seg1 + segN video combinations from a segmented Quest dataset.",
    )
    parser.add_argument("--name", required=True, help="Dataset name under ./data.")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, help="Dataset root.")
    parser.add_argument(
        "--include-aligned",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether to export a filtered aligned_frames.parquet alongside each output video.",
    )
    return parser


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_segments(dataset_dir: Path) -> list[dict]:
    payload = _load_json(dataset_dir / "segments.json")
    segments = payload.get("segments")
    if not isinstance(segments, list):
        raise SystemExit("segments.json does not contain a valid 'segments' list.")

    normalized: list[dict] = []
    for segment in segments:
        try:
            start_frame_index = int(segment["start_frame_index"])
            end_frame_index = int(segment["end_frame_index"])
            start_timestamp_ns = int(segment["start_timestamp_ns"])
            end_timestamp_ns = int(segment["end_timestamp_ns"])
            segment_index = int(segment["segment_index"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemExit(f"Invalid segment entry in segments.json: {segment}") from exc

        if end_frame_index < start_frame_index:
            raise SystemExit(f"Invalid segment frame range: {segment}")

        normalized.append(
            {
                "segment_index": segment_index,
                "label": str(segment.get("label") or f"seg{segment_index}"),
                "start_frame_index": start_frame_index,
                "end_frame_index": end_frame_index,
                "start_timestamp_ns": start_timestamp_ns,
                "end_timestamp_ns": end_timestamp_ns,
            }
        )

    normalized.sort(key=lambda item: item["segment_index"])
    return normalized


def _selected_source_indices(segments: list[dict]) -> list[int]:
    selected: list[int] = []
    for segment in segments:
        selected.extend(range(segment["start_frame_index"], segment["end_frame_index"] + 1))
    return selected


def _export_video(source_video_path: Path, output_video_path: Path, source_frame_indices: set[int], fps: float) -> int:
    reader = imageio.get_reader(source_video_path)
    writer = None
    frames_written = 0

    try:
        for frame_index, frame in enumerate(reader):
            if frame_index not in source_frame_indices:
                continue

            if writer is None:
                writer = imageio.get_writer(
                    output_video_path,
                    fps=fps,
                    codec="libx264",
                    quality=8,
                    macro_block_size=None,
                )
            writer.append_data(frame)
            frames_written += 1
    finally:
        reader.close()
        if writer is not None:
            writer.close()

    if frames_written == 0:
        raise SystemExit(f"No frames were exported for {output_video_path.parent.name}.")
    return frames_written


def _export_aligned(dataset_dir: Path, output_path: Path, source_frame_indices: list[int]) -> int:
    aligned_rows = pq.read_table(dataset_dir / "aligned_frames.parquet").to_pylist()
    rows_by_source_index = {
        int(row["camera_frame_index"]): row
        for row in aligned_rows
        if row.get("camera_frame_index") is not None
    }

    exported_rows: list[dict] = []
    for export_frame_index, source_frame_index in enumerate(source_frame_indices):
        source_row = rows_by_source_index.get(source_frame_index)
        if source_row is None:
            raise SystemExit(f"aligned_frames.parquet is missing source frame {source_frame_index}.")

        row = deepcopy(source_row)
        row["source_camera_frame_index"] = source_frame_index
        row["export_camera_frame_index"] = export_frame_index
        row["camera_frame_index"] = export_frame_index
        exported_rows.append(row)

    pq.write_table(pa.Table.from_pylist(exported_rows), output_path)
    return len(exported_rows)


def _write_manifest(
    output_path: Path,
    *,
    dataset_name: str,
    combo_name: str,
    fps: float,
    selected_segments: list[dict],
    source_frame_indices: list[int],
    frames_written: int,
    include_aligned: bool,
) -> None:
    manifest = {
        "dataset_name": dataset_name,
        "combo_name": combo_name,
        "created_at_unix_ns": time.time_ns(),
        "fps": fps,
        "video_path": "camera.mp4",
        "aligned_frames_path": "aligned_frames.parquet" if include_aligned else None,
        "source_frame_count": len(source_frame_indices),
        "export_frame_count": frames_written,
        "segments": selected_segments,
    }
    output_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _write_export_session(
    output_path: Path,
    *,
    session: dict,
    combo_name: str,
    source_frame_indices: list[int],
    include_aligned: bool,
) -> None:
    exported_session = deepcopy(session)
    exported_session["dataset_name"] = combo_name
    exported_session["video_path"] = "camera.mp4"
    exported_session["aligned_frames_path"] = "aligned_frames.parquet" if include_aligned else None
    exported_session["export_combo_name"] = combo_name
    exported_session["export_source_frame_count"] = len(source_frame_indices)
    exported_session["export_source_frame_index_start"] = source_frame_indices[0] if source_frame_indices else None
    exported_session["export_source_frame_index_end"] = source_frame_indices[-1] if source_frame_indices else None
    output_path.write_text(json.dumps(exported_session, indent=2), encoding="utf-8")


def main() -> None:
    args = _build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    dataset_dir = Path(args.output_root) / args.name
    session = _load_json(dataset_dir / "session.json")
    segments = _load_segments(dataset_dir)
    if len(segments) < 2:
        raise SystemExit("At least two segments are required to export combinations.")

    source_video_path = dataset_dir / session.get("video_path", "camera.mp4")
    fps = float(session.get("fps") or 15)
    exports_dir = dataset_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    base_segment = segments[0]
    for segment in segments[1:]:
        combo_segments = [base_segment, segment]
        source_frame_indices = _selected_source_indices(combo_segments)
        output_dir = exports_dir / f"{base_segment['label']}_{segment['label']}"
        output_dir.mkdir(parents=True, exist_ok=True)

        logging.info(
            "Exporting %s with source frames=%d",
            output_dir.name,
            len(source_frame_indices),
        )
        frames_written = _export_video(
            source_video_path=source_video_path,
            output_video_path=output_dir / "camera.mp4",
            source_frame_indices=set(source_frame_indices),
            fps=fps,
        )

        if args.include_aligned:
            aligned_rows_written = _export_aligned(
                dataset_dir=dataset_dir,
                output_path=output_dir / "aligned_frames.parquet",
                source_frame_indices=source_frame_indices,
            )
            if aligned_rows_written != frames_written:
                raise SystemExit(
                    f"Frame count mismatch for {output_dir.name}: video={frames_written}, aligned={aligned_rows_written}"
                )

        _write_export_session(
            output_path=output_dir / "session.json",
            session=session,
            combo_name=output_dir.name,
            source_frame_indices=source_frame_indices,
            include_aligned=args.include_aligned,
        )
        _write_manifest(
            output_path=output_dir / "export_manifest.json",
            dataset_name=args.name,
            combo_name=output_dir.name,
            fps=fps,
            selected_segments=combo_segments,
            source_frame_indices=source_frame_indices,
            frames_written=frames_written,
            include_aligned=args.include_aligned,
        )
        logging.info("Finished %s frames=%d", output_dir.name, frames_written)


if __name__ == "__main__":
    main()
