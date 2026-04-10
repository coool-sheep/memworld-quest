"""Record Quest camera, hand, and head streams into ./data/{name}.

The script:
    - listens for HTS hand/head TCP telemetry
    - listens for Quest camera TCP/JPEG frames
    - previews the incoming camera image live
    - writes camera.mp4 plus parquet tables for raw and aligned data

Usage:
    python ./scripts/record_quest_dataset.py --name demo
    python ./scripts/record_quest_dataset.py --name demo --output-root ./data --fps 15
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import socket
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import imageio.v2 as imageio
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image

from hts_dataset_utils import (
    calibration_to_projection_defaults,
    camera_pose_from_head,
    default_camera_offset,
    euler_deg_to_quat,
    finger_segment_indices,
    intrinsics_from_fov,
    landmarks_local_to_world,
    parse_hts_line,
)
from quest_camera_receiver import handle_camera_client_stream

DEFAULT_OUTPUT_ROOT = "./data"
DEFAULT_DATASET_FPS = 15
DEFAULT_HAND_HOST = "127.0.0.1"
DEFAULT_HAND_PORT = 8000
DEFAULT_CAMERA_HOST = "127.0.0.1"
DEFAULT_CAMERA_PORT = 8765
DEFAULT_CAMERA_EYE = "left"
DEFAULT_FOV_X_DEG = 90.0
DEFAULT_FOV_Y_DEG = 70.0
DEFAULT_CAMERA_PITCH_DEG = 0.0
DEFAULT_CAMERA_YAW_DEG = 0.0
DEFAULT_CAMERA_ROLL_DEG = 0.0
DEFAULT_ENABLE_PREVIEW = True
DEFAULT_VIDEO_WIDTH = 640
DEFAULT_VIDEO_HEIGHT = 480
PIL_RESAMPLING = getattr(Image, "Resampling", Image)


@dataclass
class TelemetrySample:
    frame_id: int | None
    timestamp_ns: int
    values: list[float]


@dataclass
class CameraFrame:
    frame_id: int
    timestamp_ns: int
    width: int
    height: int
    jpeg_bytes: bytes
    received_at_ns: int


class TimedSampleBuffer:
    def __init__(self, maxlen: int = 512) -> None:
        self._samples: deque[TelemetrySample] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(self, sample: TelemetrySample) -> None:
        with self._lock:
            self._samples.append(sample)

    def nearest(self, timestamp_ns: int) -> TelemetrySample | None:
        with self._lock:
            if not self._samples:
                return None
            return min(self._samples, key=lambda sample: abs(sample.timestamp_ns - timestamp_ns))


class TelemetryServer:
    def __init__(self, host: str, port: int, on_sample: Callable[[str, str, TelemetrySample, str], None]) -> None:
        self.host = host
        self.port = port
        self.on_sample = on_sample
        self._stop_event = threading.Event()
        self._server_socket: socket.socket | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._connections: list[threading.Thread] = []

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(5)
        self._server_socket.settimeout(0.5)
        logging.info("Telemetry TCP server listening on tcp://%s:%d", self.host, self.port)

        while not self._stop_event.is_set():
            try:
                conn, addr = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            thread = threading.Thread(
                target=self._handle_connection,
                args=(conn, addr),
                daemon=True,
            )
            self._connections.append(thread)
            thread.start()

    def _handle_connection(self, conn: socket.socket, addr) -> None:
        logging.info("Telemetry client connected from %s:%d", addr[0], addr[1])
        buffer = ""
        with conn:
            conn.settimeout(0.5)
            while not self._stop_event.is_set():
                try:
                    chunk = conn.recv(4096)
                except socket.timeout:
                    continue
                except OSError:
                    break

                if not chunk:
                    break

                try:
                    buffer += chunk.decode("utf-8")
                except UnicodeDecodeError:
                    continue

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    parsed = parse_hts_line(line.strip())
                    if parsed is None:
                        continue
                    timestamp_ns = parsed.timestamp_ns or time.monotonic_ns()
                    sample = TelemetrySample(
                        frame_id=parsed.frame_id,
                        timestamp_ns=timestamp_ns,
                        values=parsed.values,
                    )
                    self.on_sample(parsed.stream, parsed.kind, sample, parsed.raw_label)

        logging.info("Telemetry client closed from %s:%d", addr[0], addr[1])


class CameraTcpReceiver:
    def __init__(
        self,
        host: str,
        port: int,
        on_frame: Callable[[CameraFrame], None],
        on_metadata: Callable[[dict], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.on_frame = on_frame
        self.on_metadata = on_metadata
        self._stop_event = threading.Event()
        self._server_socket: socket.socket | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(1)
        self._server_socket.settimeout(0.5)
        logging.info("Camera TCP receiver listening on tcp://%s:%d", self.host, self.port)

        while not self._stop_event.is_set():
            try:
                conn, addr = self._server_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            logging.info("Camera client connected from %s:%d", addr[0], addr[1])
            try:
                self._handle_client(conn)
            except ConnectionError as exc:
                logging.warning("Camera client disconnected: %s", exc)
            except Exception:
                logging.exception("Unexpected camera receiver error.")
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
                logging.info("Camera client closed from %s:%d", addr[0], addr[1])

    def _handle_client(self, conn: socket.socket) -> None:
        def on_frame(width: int, height: int, frame_id: int, timestamp_ns: int, jpeg_bytes: bytes) -> None:
            self.on_frame(
                CameraFrame(
                    frame_id=frame_id,
                    timestamp_ns=timestamp_ns,
                    width=width,
                    height=height,
                    jpeg_bytes=jpeg_bytes,
                    received_at_ns=time.monotonic_ns(),
                )
            )

        def on_metadata(metadata: dict) -> None:
            if self.on_metadata is not None:
                self.on_metadata(metadata)

        handle_camera_client_stream(
            conn,
            on_frame=on_frame,
            on_metadata=on_metadata,
            should_stop=self._stop_event.is_set,
        )


class DatasetRecorder:
    def __init__(self, output_dir: Path, args: argparse.Namespace) -> None:
        self.output_dir = output_dir
        self.args = args
        self.telemetry_buffers = {
            ("head", "pose"): TimedSampleBuffer(),
            ("left", "wrist"): TimedSampleBuffer(),
            ("left", "landmarks"): TimedSampleBuffer(),
            ("right", "wrist"): TimedSampleBuffer(),
            ("right", "landmarks"): TimedSampleBuffer(),
        }
        self.telemetry_rows: list[dict] = []
        self.camera_rows: list[dict] = []
        self.aligned_rows: list[dict] = []
        self._latest_preview_rgb: np.ndarray | None = None
        self._preview_lock = threading.Lock()
        self._writer = None
        self._session_started_ns = time.time_ns()
        self._frame_counter = 0
        self._fps_started_at = time.monotonic()
        self._camera_rotation_offset = euler_deg_to_quat(
            DEFAULT_CAMERA_PITCH_DEG,
            DEFAULT_CAMERA_YAW_DEG,
            DEFAULT_CAMERA_ROLL_DEG,
        )
        self._camera_offset = default_camera_offset(DEFAULT_CAMERA_EYE)
        self._intrinsics: dict[str, float] | None = None
        self._video_path = self.output_dir / "camera.mp4"
        self._telemetry_lock = threading.Lock()
        self._camera_metadata: dict | None = None
        self._pending_camera_pose_by_frame_id: dict[int, dict] = {}

    def on_telemetry_sample(self, stream: str, kind: str, sample: TelemetrySample, raw_label: str) -> None:
        key = (stream, kind)
        if key in self.telemetry_buffers:
            self.telemetry_buffers[key].append(sample)

        row = {
            "stream": stream,
            "kind": kind,
            "frame_id": sample.frame_id,
            "timestamp_ns": sample.timestamp_ns,
            "raw_label": raw_label,
            "values": list(sample.values),
        }
        with self._telemetry_lock:
            self.telemetry_rows.append(row)

    def on_camera_frame(self, frame: CameraFrame) -> None:
        image = Image.open(io.BytesIO(frame.jpeg_bytes)).convert("RGB")
        rgb = np.asarray(image)
        self._ensure_writer(frame.width, frame.height)
        self._writer.append_data(self._resize_for_video(image))

        with self._preview_lock:
            self._latest_preview_rgb = rgb

        self._frame_counter += 1
        self.camera_rows.append(
            {
                "camera_frame_index": len(self.camera_rows),
                "camera_frame_id": frame.frame_id,
                "camera_timestamp_ns": frame.timestamp_ns,
                "camera_received_at_ns": frame.received_at_ns,
                "width": frame.width,
                "height": frame.height,
            }
        )
        self.aligned_rows.append(self._build_aligned_row(frame))

        elapsed = max(time.monotonic() - self._fps_started_at, 1e-6)
        if self._frame_counter % max(int(self.args.fps), 1) == 0:
            logging.info(
                "Recorded camera frames=%d avg_fps=%.2f",
                self._frame_counter,
                self._frame_counter / elapsed,
            )

    def on_camera_metadata(self, metadata: dict) -> None:
        packet_type = metadata.get("packet_type")
        if packet_type == "camera_calibration":
            self._camera_metadata = metadata
            exact_intrinsics = calibration_to_projection_defaults(metadata)
            if exact_intrinsics is not None:
                self._intrinsics = exact_intrinsics
            logging.info("Received camera calibration metadata source=%s", metadata.get("source", "unknown"))
            return

        if packet_type == "camera_pose":
            frame_id = metadata.get("frame_id")
            if isinstance(frame_id, int):
                self._pending_camera_pose_by_frame_id[frame_id] = metadata
                if len(self._pending_camera_pose_by_frame_id) > 512:
                    oldest = next(iter(self._pending_camera_pose_by_frame_id))
                    self._pending_camera_pose_by_frame_id.pop(oldest, None)
            return

        logging.info("Received unhandled camera metadata packet_type=%s", packet_type)

    def latest_preview_rgb(self) -> np.ndarray | None:
        with self._preview_lock:
            if self._latest_preview_rgb is None:
                return None
            return self._latest_preview_rgb.copy()

    def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        self._write_outputs()

    def _ensure_writer(self, width: int, height: int) -> None:
        if self._writer is not None:
            return
        if self._intrinsics is None:
            exact_intrinsics = calibration_to_projection_defaults(self._camera_metadata)
            self._intrinsics = exact_intrinsics or intrinsics_from_fov(
                width,
                height,
                DEFAULT_FOV_X_DEG,
                DEFAULT_FOV_Y_DEG,
            )
        self._writer = imageio.get_writer(
            self._video_path,
            fps=self.args.fps,
            codec="libx264",
            quality=8,
            macro_block_size=None,
        )

    @staticmethod
    def _resize_for_video(image: Image.Image) -> np.ndarray:
        resized = image.resize((DEFAULT_VIDEO_WIDTH, DEFAULT_VIDEO_HEIGHT), PIL_RESAMPLING.BILINEAR)
        return np.asarray(resized)

    def _build_aligned_row(self, frame: CameraFrame) -> dict:
        row: dict[str, object] = {
            "camera_frame_index": len(self.aligned_rows),
            "camera_frame_id": frame.frame_id,
            "camera_timestamp_ns": frame.timestamp_ns,
            "camera_received_at_ns": frame.received_at_ns,
            "camera_width": frame.width,
            "camera_height": frame.height,
        }

        head = self.telemetry_buffers[("head", "pose")].nearest(frame.timestamp_ns)
        self._append_pose(row, "head", head, expected_values=7, reference_timestamp_ns=frame.timestamp_ns)

        for side in ("left", "right"):
            wrist = self.telemetry_buffers[(side, "wrist")].nearest(frame.timestamp_ns)
            landmarks = self.telemetry_buffers[(side, "landmarks")].nearest(frame.timestamp_ns)
            self._append_pose(
                row,
                f"{side}_wrist",
                wrist,
                expected_values=7,
                reference_timestamp_ns=frame.timestamp_ns,
            )
            self._append_landmarks(row, side, wrist, landmarks, reference_timestamp_ns=frame.timestamp_ns)

        if head is not None and len(head.values) >= 7:
            calibration = self._camera_metadata or {}
            lens_offset_position = calibration.get("lens_offset_position") or self._camera_offset.tolist()
            lens_offset_rotation = calibration.get("lens_offset_rotation") or self._camera_rotation_offset.tolist()
            camera_position, camera_quaternion = camera_pose_from_head(
                head.values[:3],
                head.values[3:7],
                lens_offset_position,
                lens_offset_rotation,
            )
            row["camera_position_world"] = camera_position.tolist()
            row["camera_quaternion_world"] = camera_quaternion.tolist()
        else:
            row["camera_position_world"] = None
            row["camera_quaternion_world"] = None

        frame_pose = self._pending_camera_pose_by_frame_id.pop(frame.frame_id, None)
        if frame_pose is not None:
            row["camera_pose_source"] = "quest_frame_pose"
            row["camera_position_world"] = frame_pose.get("position_world")
            row["camera_quaternion_world"] = frame_pose.get("rotation_world")
            row["camera_pose_timestamp_ns"] = frame_pose.get("timestamp_ns")
        else:
            row["camera_pose_source"] = "head_pose_plus_lens_offset"
            row["camera_pose_timestamp_ns"] = frame.timestamp_ns

        return row

    @staticmethod
    def _append_pose(
        row: dict,
        prefix: str,
        sample: TelemetrySample | None,
        expected_values: int,
        reference_timestamp_ns: int,
    ) -> None:
        row[f"{prefix}_frame_id"] = sample.frame_id if sample is not None else None
        row[f"{prefix}_timestamp_ns"] = sample.timestamp_ns if sample is not None else None
        row[f"{prefix}_dt_ms"] = (
            (sample.timestamp_ns - reference_timestamp_ns) / 1_000_000.0 if sample is not None else None
        )
        if sample is None or len(sample.values) < expected_values:
            row[f"{prefix}_position"] = None
            row[f"{prefix}_quaternion"] = None
            return
        row[f"{prefix}_position"] = list(sample.values[:3])
        row[f"{prefix}_quaternion"] = list(sample.values[3:7])

    @staticmethod
    def _flatten_points(points: np.ndarray | None) -> list[float] | None:
        if points is None:
            return None
        return np.asarray(points, dtype=np.float64).reshape(-1).tolist()

    def _append_landmarks(
        self,
        row: dict,
        side: str,
        wrist: TelemetrySample | None,
        landmarks: TelemetrySample | None,
        reference_timestamp_ns: int,
    ) -> None:
        row[f"{side}_landmarks_frame_id"] = landmarks.frame_id if landmarks is not None else None
        row[f"{side}_landmarks_timestamp_ns"] = landmarks.timestamp_ns if landmarks is not None else None
        row[f"{side}_landmarks_dt_ms"] = (
            (landmarks.timestamp_ns - reference_timestamp_ns) / 1_000_000.0 if landmarks is not None else None
        )

        if landmarks is None or not landmarks.values:
            row[f"{side}_landmarks_local"] = None
            row[f"{side}_landmarks_world"] = None
            return

        row[f"{side}_landmarks_local"] = list(landmarks.values)

        if wrist is None or len(wrist.values) < 7:
            row[f"{side}_landmarks_world"] = None
            return

        world = landmarks_local_to_world(
            wrist_position=wrist.values[:3],
            wrist_quaternion=wrist.values[3:7],
            landmarks_local=landmarks.values,
        )
        row[f"{side}_landmarks_world"] = self._flatten_points(world)

    def _write_outputs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

        telemetry_table = pa.Table.from_pylist(self.telemetry_rows)
        camera_table = pa.Table.from_pylist(self.camera_rows)
        aligned_table = pa.Table.from_pylist(self.aligned_rows)
        pq.write_table(telemetry_table, self.output_dir / "telemetry_raw.parquet")
        pq.write_table(camera_table, self.output_dir / "camera_frames.parquet")
        pq.write_table(aligned_table, self.output_dir / "aligned_frames.parquet")

        session = {
            "dataset_name": self.args.name,
            "created_at_unix_ns": self._session_started_ns,
            "video_path": self._video_path.name,
            "video_resolution": {
                "width": DEFAULT_VIDEO_WIDTH,
                "height": DEFAULT_VIDEO_HEIGHT,
            },
            "hand_endpoint": {
                "host": DEFAULT_HAND_HOST,
                "port": DEFAULT_HAND_PORT,
            },
            "camera_endpoint": {
                "host": DEFAULT_CAMERA_HOST,
                "port": DEFAULT_CAMERA_PORT,
            },
            "fps": self.args.fps,
            "camera_eye": DEFAULT_CAMERA_EYE,
            "camera_offset_local_m": self._camera_offset.tolist(),
            "camera_rotation_offset_quaternion": self._camera_rotation_offset.tolist(),
            "camera_rotation_offset_euler_deg": {
                "pitch": DEFAULT_CAMERA_PITCH_DEG,
                "yaw": DEFAULT_CAMERA_YAW_DEG,
                "roll": DEFAULT_CAMERA_ROLL_DEG,
            },
            "projection_defaults": self._intrinsics,
            "projection_source": (
                "quest_camera_calibration_metadata"
                if self._camera_metadata is not None
                else "approximate_defaults_in_code"
            ),
            "camera_calibration": self._camera_metadata,
            "finger_segment_indices": [
                [start, end] for start, end in finger_segment_indices(21)
            ],
            "notes": (
                "Camera video is stored as camera.mp4. Projection currently uses head pose plus "
                "camera calibration metadata when available, otherwise falls back to approximate defaults."
            ),
        }
        (self.output_dir / "session.json").write_text(
            json.dumps(session, indent=2),
            encoding="utf-8",
        )
        logging.info("Dataset written to %s", self.output_dir)


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="record_quest_dataset",
        description="Record Quest camera, hand, and head streams into a dataset folder.",
    )
    parser.add_argument("--name", required=True, help="Dataset name. Output will be ./data/{name}.")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, help="Root folder for datasets.")
    parser.add_argument("--fps", type=int, default=DEFAULT_DATASET_FPS, help="Dataset video/playback fps.")
    return parser


def _run_preview_loop(recorder: DatasetRecorder) -> None:
    import matplotlib.pyplot as plt

    plt.ion()
    figure, axis = plt.subplots()
    image_artist = None
    stop_requested = False

    def _handle_key_press(event) -> None:
        nonlocal stop_requested
        if event.key == "q":
            stop_requested = True
            plt.close(figure)

    figure.canvas.mpl_connect("key_press_event", _handle_key_press)

    while not stop_requested and plt.fignum_exists(figure.number):
        frame = recorder.latest_preview_rgb()
        if frame is not None:
            if image_artist is None:
                image_artist = axis.imshow(frame)
                axis.axis("off")
                axis.set_title("Quest Recorder Preview")
            else:
                image_artist.set_data(frame)
            figure.canvas.draw_idle()
        plt.pause(0.03)


def main() -> None:
    args = _create_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    output_dir = Path(args.output_root) / args.name
    output_dir.mkdir(parents=True, exist_ok=True)
    recorder = DatasetRecorder(output_dir=output_dir, args=args)
    telemetry_server = TelemetryServer(
        host=DEFAULT_HAND_HOST,
        port=DEFAULT_HAND_PORT,
        on_sample=recorder.on_telemetry_sample,
    )
    camera_receiver = CameraTcpReceiver(
        host=DEFAULT_CAMERA_HOST,
        port=DEFAULT_CAMERA_PORT,
        on_frame=recorder.on_camera_frame,
        on_metadata=recorder.on_camera_metadata,
    )

    telemetry_server.start()
    camera_receiver.start()

    if DEFAULT_ENABLE_PREVIEW:
        logging.info("Waiting for Quest streams. Focus the preview window and press q, or press Ctrl+C to stop recording.")
    else:
        logging.info("Waiting for Quest streams. Press Ctrl+C to stop recording.")
    logging.info("ADB reverse commands:")
    logging.info("  adb reverse tcp:%d tcp:%d", DEFAULT_HAND_PORT, DEFAULT_HAND_PORT)
    logging.info("  adb reverse tcp:%d tcp:%d", DEFAULT_CAMERA_PORT, DEFAULT_CAMERA_PORT)

    try:
        if DEFAULT_ENABLE_PREVIEW:
            _run_preview_loop(recorder)
        else:
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        logging.info("Stopping recorder.")
    finally:
        camera_receiver.stop()
        telemetry_server.stop()
        recorder.close()


if __name__ == "__main__":
    main()
