"""Replay a recorded dataset and project hand data back into the camera image.

Usage:
    python ./scripts/reproject_quest_dataset.py --name demo
    python ./scripts/reproject_quest_dataset.py --name demo --output-root ./data --fps 15
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
import pyarrow.parquet as pq
from PIL import Image, ImageDraw

from hts_dataset_utils import (
    camera_pose_from_head,
    default_camera_offset,
    finger_segment_indices,
    project_world_to_image_with_calibration,
)


DEFAULT_OUTPUT_ROOT = "./data"
DEFAULT_DATASET_FPS = 15
DEFAULT_CAMERA_EYE = "left"
DEFAULT_CAMERA_OFFSET = default_camera_offset(DEFAULT_CAMERA_EYE)
DEFAULT_CAMERA_ROTATION_OFFSET = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64)


def _draw_hand_overlay(
    image: Image.Image,
    wrist_position: list[float] | None,
    landmarks_world: list[float] | None,
    camera_position: np.ndarray,
    camera_quaternion: np.ndarray,
    calibration: dict,
    point_color: tuple[int, int, int],
    line_color: tuple[int, int, int],
) -> None:
    if wrist_position is None or landmarks_world is None:
        return

    wrist = np.asarray(wrist_position, dtype=np.float64)
    landmarks = np.asarray(landmarks_world, dtype=np.float64)
    if landmarks.size < 3:
        return
    landmarks = landmarks.reshape((-1, 3))

    projected_landmarks, landmark_valid = project_world_to_image_with_calibration(
        landmarks,
        camera_position=camera_position,
        camera_quaternion=camera_quaternion,
        calibration=calibration,
        image_width=image.width,
        image_height=image.height,
    )
    projected_wrist, wrist_valid = project_world_to_image_with_calibration(
        wrist.reshape(1, 3),
        camera_position=camera_position,
        camera_quaternion=camera_quaternion,
        calibration=calibration,
        image_width=image.width,
        image_height=image.height,
    )

    draw = ImageDraw.Draw(image)
    wrist_xy = tuple(projected_wrist[0].tolist())
    if wrist_valid[0]:
        draw.ellipse(
            (wrist_xy[0] - 4, wrist_xy[1] - 4, wrist_xy[0] + 4, wrist_xy[1] + 4),
            fill=line_color,
        )

    for start, end in finger_segment_indices(len(landmarks)):
        if start == "wrist":
            start_xy = wrist_xy
            start_valid = wrist_valid[0]
        else:
            start_xy = tuple(projected_landmarks[start].tolist())
            start_valid = landmark_valid[start]
        end_xy = tuple(projected_landmarks[end].tolist())
        end_valid = landmark_valid[end]
        if start_valid and end_valid:
            draw.line((start_xy[0], start_xy[1], end_xy[0], end_xy[1]), fill=line_color, width=2)

    for index, is_valid in enumerate(landmark_valid):
        if not is_valid:
            continue
        x, y = projected_landmarks[index]
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=point_color)


def _resolve_intrinsics(
    session: dict,
    source_width: int | None,
    source_height: int | None,
    frame_width: int,
    frame_height: int,
) -> dict:
    source_width = int(source_width or frame_width)
    source_height = int(source_height or frame_height)

    calibration = session.get("camera_calibration")
    if calibration is not None:
        calibration = dict(calibration)
        calibration.setdefault("current_resolution", [source_width, source_height])
        return calibration

    defaults = session.get("projection_defaults") or {}
    if "fx" not in defaults or "fy" not in defaults:
        raise SystemExit("Missing camera calibration in session.json.")

    return {
        "current_resolution": [source_width, source_height],
        "sensor_resolution": [source_width, source_height],
        "focal_length": [
            float(defaults["fx"]),
            float(defaults["fy"]),
        ],
        "principal_point": [
            float(defaults.get("cx", source_width * 0.5)),
            float(defaults.get("cy", source_height * 0.5)),
        ],
        "lens_offset_position": session.get("camera_offset_local_m") or DEFAULT_CAMERA_OFFSET.tolist(),
        "lens_offset_rotation": session.get("camera_rotation_offset_quaternion") or DEFAULT_CAMERA_ROTATION_OFFSET.tolist(),
    }


def _load_session(dataset_dir: Path) -> dict:
    session_path = dataset_dir / "session.json"
    if not session_path.exists():
        return {}
    return json.loads(session_path.read_text(encoding="utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reproject_quest_dataset",
        description="Replay a recorded Quest dataset and project hands back into the image.",
    )
    parser.add_argument("--name", required=True, help="Dataset name under ./data.")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, help="Dataset root.")
    parser.add_argument("--fps", type=float, default=DEFAULT_DATASET_FPS, help="Dataset playback fps.")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    dataset_dir = Path(args.output_root) / args.name

    session = _load_session(dataset_dir)
    aligned_rows = pq.read_table(dataset_dir / "aligned_frames.parquet").to_pylist()
    video_path = dataset_dir / session.get("video_path", "camera.mp4")
    reader = imageio.get_reader(video_path)

    import matplotlib.pyplot as plt

    plt.ion()
    display, axis = plt.subplots()
    axis.axis("off")
    image_artist = None
    pause_seconds = 1.0 / float(args.fps)

    try:
        for index, frame in enumerate(reader):
            if index >= len(aligned_rows):
                break

            row = aligned_rows[index]
            pil_image = Image.fromarray(frame).convert("RGB")
            calibration = _resolve_intrinsics(
                session,
                source_width=row.get("camera_width"),
                source_height=row.get("camera_height"),
                frame_width=pil_image.width,
                frame_height=pil_image.height,
            )
            calibration = _resolve_intrinsics(
                session,
                source_width=row.get("camera_width"),
                source_height=row.get("camera_height"),
                frame_width=pil_image.width,
                frame_height=pil_image.height,
            )

            camera_position = row.get("camera_position_world")
            camera_quaternion = row.get("camera_quaternion_world")
            if camera_position is None or camera_quaternion is None:
                head_position = row.get("head_position")
                head_quaternion = row.get("head_quaternion")
                if head_position is None or head_quaternion is None:
                    camera_position = None
                    camera_quaternion = None
                else:
                    lens_offset_position = calibration.get("lens_offset_position") or DEFAULT_CAMERA_OFFSET.tolist()
                    lens_offset_rotation = calibration.get("lens_offset_rotation") or DEFAULT_CAMERA_ROTATION_OFFSET.tolist()
                    camera_position, camera_quaternion = camera_pose_from_head(
                        head_position,
                        head_quaternion,
                        lens_offset_position,
                        lens_offset_rotation,
                    )

            if camera_position is not None and camera_quaternion is not None:
                camera_position = np.asarray(camera_position, dtype=np.float64)
                camera_quaternion = np.asarray(camera_quaternion, dtype=np.float64)
                _draw_hand_overlay(
                    pil_image,
                    row.get("left_wrist_position"),
                    row.get("left_landmarks_world"),
                    camera_position,
                    camera_quaternion,
                    calibration,
                    point_color=(90, 170, 255),
                    line_color=(40, 100, 220),
                )
                _draw_hand_overlay(
                    pil_image,
                    row.get("right_wrist_position"),
                    row.get("right_landmarks_world"),
                    camera_position,
                    camera_quaternion,
                    calibration,
                    point_color=(255, 165, 70),
                    line_color=(220, 90, 20),
                )

            if image_artist is None:
                image_artist = axis.imshow(pil_image)
            else:
                image_artist.set_data(pil_image)
            axis.set_title(f"Quest Dataset Replay - frame {index}")
            display.canvas.draw_idle()
            display.canvas.flush_events()
            plt.pause(pause_seconds)
    finally:
        reader.close()


if __name__ == "__main__":
    main()
