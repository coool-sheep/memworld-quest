"""Generate per-segment contact sheets from a segmented Quest recording.

Usage:
    python ./scripts/generate_segment_contact_sheets.py --name demo
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw


DEFAULT_OUTPUT_ROOT = "./data"
MAX_FRAMES_PER_SHEET = 32
SEG1_UNIFORM_SAMPLES = 32
OTHER_SEGMENT_STRIDE = 4
SHEET_ROWS = 4
SHEET_COLS = 8
THUMBNAIL_WIDTH = 240
THUMBNAIL_HEIGHT = 180
SHEET_PADDING = 12
LABEL_HEIGHT = 22
BACKGROUND_COLOR = (18, 18, 18)
TEXT_COLOR = (245, 245, 245)
EMPTY_TILE_COLOR = (35, 35, 35)
FRAME_BORDER_COLOR = (70, 70, 70)
PIL_RESAMPLING = getattr(Image, "Resampling", Image)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate_segment_contact_sheets",
        description="Generate per-segment contact sheets from a segmented Quest recording.",
    )
    parser.add_argument("--name", required=True, help="Dataset name under ./data.")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, help="Dataset root.")
    return parser


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_segments(dataset_dir: Path) -> list[dict]:
    payload = _load_json(dataset_dir / "segments.json")
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        raise SystemExit("segments.json does not contain a valid non-empty 'segments' list.")

    normalized: list[dict] = []
    for segment in segments:
        try:
            segment_index = int(segment["segment_index"])
            start_frame_index = int(segment["start_frame_index"])
            end_frame_index = int(segment["end_frame_index"])
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
            }
        )

    normalized.sort(key=lambda item: item["segment_index"])
    return normalized


def _uniform_sample_indices(start: int, end: int, sample_count: int) -> list[int]:
    frame_count = (end - start) + 1
    if frame_count <= 0:
        return []
    if frame_count <= sample_count:
        return list(range(start, end + 1))

    sample_positions = np.linspace(start, end, num=sample_count)
    sampled = [int(round(position)) for position in sample_positions]

    deduplicated: list[int] = []
    seen: set[int] = set()
    for frame_index in sampled:
        if frame_index in seen:
            continue
        deduplicated.append(frame_index)
        seen.add(frame_index)
    return deduplicated


def _stride_sample_indices(start: int, end: int, stride: int) -> list[int]:
    if end < start:
        return []
    return list(range(start, end + 1, max(stride, 1)))


def _chunked(items: list[int], chunk_size: int) -> list[list[int]]:
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _collect_frames(video_path: Path, frame_indices: set[int]) -> dict[int, Image.Image]:
    reader = imageio.get_reader(video_path)
    captured: dict[int, Image.Image] = {}

    try:
        for frame_index, frame in enumerate(reader):
            if frame_index not in frame_indices:
                continue
            captured[frame_index] = Image.fromarray(frame).convert("RGB")
            if len(captured) == len(frame_indices):
                break
    finally:
        reader.close()

    missing = sorted(frame_indices - captured.keys())
    if missing:
        raise SystemExit(f"Failed to read sampled frames from video: missing {missing[:8]}")
    return captured


def _draw_tile(
    canvas: Image.Image,
    *,
    tile_left: int,
    tile_top: int,
    frame_image: Image.Image | None,
    frame_index: int | None,
    draw: ImageDraw.ImageDraw,
) -> None:
    tile_box = (
        tile_left,
        tile_top,
        tile_left + THUMBNAIL_WIDTH - 1,
        tile_top + THUMBNAIL_HEIGHT - 1,
    )
    if frame_image is None:
        draw.rectangle(tile_box, fill=EMPTY_TILE_COLOR, outline=FRAME_BORDER_COLOR, width=1)
        return

    resized = frame_image.resize((THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), PIL_RESAMPLING.BILINEAR)
    canvas.paste(resized, (tile_left, tile_top))
    draw.rectangle(tile_box, outline=FRAME_BORDER_COLOR, width=1)
    if frame_index is not None:
        draw.text(
            (tile_left + 6, tile_top + 4),
            f"f={frame_index}",
            fill=TEXT_COLOR,
        )


def _render_sheet(
    *,
    segment_label: str,
    sheet_index: int,
    total_sheets: int,
    sampled_indices: list[int],
    frame_lookup: dict[int, Image.Image],
    output_path: Path,
) -> None:
    width = (THUMBNAIL_WIDTH * SHEET_COLS) + (SHEET_PADDING * (SHEET_COLS + 1))
    height = (
        LABEL_HEIGHT
        + (THUMBNAIL_HEIGHT * SHEET_ROWS)
        + (SHEET_PADDING * (SHEET_ROWS + 2))
    )
    canvas = Image.new("RGB", (width, height), BACKGROUND_COLOR)
    draw = ImageDraw.Draw(canvas)

    title = f"{segment_label}  sheet {sheet_index}/{total_sheets}  sampled_frames={len(sampled_indices)}"
    draw.text((SHEET_PADDING, SHEET_PADDING), title, fill=TEXT_COLOR)

    tiles = sampled_indices + ([None] * max(MAX_FRAMES_PER_SHEET - len(sampled_indices), 0))
    tile_origin_y = SHEET_PADDING + LABEL_HEIGHT
    for tile_index, frame_index in enumerate(tiles[:MAX_FRAMES_PER_SHEET]):
        row = tile_index // SHEET_COLS
        col = tile_index % SHEET_COLS
        tile_left = SHEET_PADDING + col * (THUMBNAIL_WIDTH + SHEET_PADDING)
        tile_top = tile_origin_y + row * (THUMBNAIL_HEIGHT + SHEET_PADDING)
        frame_image = frame_lookup.get(frame_index) if frame_index is not None else None
        _draw_tile(
            canvas,
            tile_left=tile_left,
            tile_top=tile_top,
            frame_image=frame_image,
            frame_index=frame_index,
            draw=draw,
        )

    canvas.save(output_path)


def main() -> None:
    args = _build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    dataset_dir = Path(args.output_root) / args.name
    session = _load_json(dataset_dir / "session.json")
    segments = _load_segments(dataset_dir)
    source_video_path = dataset_dir / session.get("video_path", "camera.mp4")
    inspection_dir = dataset_dir / "inspection"
    inspection_dir.mkdir(parents=True, exist_ok=True)

    segment_plans: list[dict] = []
    all_sampled_indices: set[int] = set()

    for segment in segments:
        if segment["segment_index"] == 1:
            sampled_indices = _uniform_sample_indices(
                segment["start_frame_index"],
                segment["end_frame_index"],
                SEG1_UNIFORM_SAMPLES,
            )
            sampling_rule = f"uniform_{SEG1_UNIFORM_SAMPLES}"
        else:
            sampled_indices = _stride_sample_indices(
                segment["start_frame_index"],
                segment["end_frame_index"],
                OTHER_SEGMENT_STRIDE,
            )
            sampling_rule = f"every_{OTHER_SEGMENT_STRIDE}_frames"

        sheet_frame_groups = _chunked(sampled_indices, MAX_FRAMES_PER_SHEET)
        segment_plans.append(
            {
                "segment_index": segment["segment_index"],
                "segment_label": segment["label"],
                "sampling_rule": sampling_rule,
                "source_frame_index_start": segment["start_frame_index"],
                "source_frame_index_end": segment["end_frame_index"],
                "sampled_frame_indices": sampled_indices,
                "sheet_count": len(sheet_frame_groups),
                "sheet_frames": sheet_frame_groups,
            }
        )
        all_sampled_indices.update(sampled_indices)

    frame_lookup = _collect_frames(source_video_path, all_sampled_indices)
    manifest_segments: list[dict] = []

    for plan in segment_plans:
        segment_label = plan["segment_label"]
        sheet_frames: list[list[int]] = plan["sheet_frames"]
        total_sheets = max(len(sheet_frames), 1)
        logging.info(
            "Generating inspection sheets for %s sampled_frames=%d sheets=%d",
            segment_label,
            len(plan["sampled_frame_indices"]),
            total_sheets,
        )

        sheet_paths: list[str] = []
        if not sheet_frames:
            sheet_frames = [[]]

        for sheet_offset, sampled_indices in enumerate(sheet_frames, start=1):
            output_path = inspection_dir / f"{segment_label}_sheet{sheet_offset:02d}.png"
            _render_sheet(
                segment_label=segment_label,
                sheet_index=sheet_offset,
                total_sheets=total_sheets,
                sampled_indices=sampled_indices,
                frame_lookup=frame_lookup,
                output_path=output_path,
            )
            sheet_paths.append(output_path.name)

        manifest_segments.append(
            {
                "segment_index": plan["segment_index"],
                "segment_label": segment_label,
                "sampling_rule": plan["sampling_rule"],
                "source_frame_index_start": plan["source_frame_index_start"],
                "source_frame_index_end": plan["source_frame_index_end"],
                "sampled_frame_count": len(plan["sampled_frame_indices"]),
                "sampled_frame_indices": plan["sampled_frame_indices"],
                "sheet_count": len(sheet_paths),
                "sheet_paths": sheet_paths,
            }
        )

    manifest = {
        "dataset_name": args.name,
        "created_at_unix_ns": time.time_ns(),
        "video_path": source_video_path.name,
        "inspection_dir": inspection_dir.name,
        "max_frames_per_sheet": MAX_FRAMES_PER_SHEET,
        "seg1_sampling_rule": f"uniform_{SEG1_UNIFORM_SAMPLES}",
        "other_segment_sampling_rule": f"every_{OTHER_SEGMENT_STRIDE}_frames",
        "sheet_layout": {
            "rows": SHEET_ROWS,
            "cols": SHEET_COLS,
            "thumbnail_width": THUMBNAIL_WIDTH,
            "thumbnail_height": THUMBNAIL_HEIGHT,
        },
        "segments": manifest_segments,
    }
    (inspection_dir / "inspection_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    logging.info("Inspection sheets written to %s", inspection_dir)


if __name__ == "__main__":
    main()
