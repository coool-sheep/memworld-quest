"""Receive Quest camera uplink over a fixed TCP port.

Usage:
    python ./scripts/quest_camera_receiver.py --host 0.0.0.0 --port 8765
    python ./scripts/quest_camera_receiver.py --host 0.0.0.0 --port 8765 --display
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import socket
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency. Please install pillow.") from exc


FRAME_MAGIC = 0x4D414351
METADATA_MAGIC = 0x41544D51
PROTOCOL_VERSION = 1
HEADER_STRUCT = struct.Struct("<IBBHHBBIQI")
METADATA_HEADER_STRUCT = struct.Struct("<IBBHI")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="quest_camera_receiver",
        description="Receive Quest camera uplink over a fixed TCP port.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host/IP to bind the TCP server to.")
    parser.add_argument("--port", type=int, default=8765, help="TCP listening port.")
    parser.add_argument(
        "--display",
        action="store_true",
        help="Display received JPEG frames with matplotlib.",
    )
    parser.add_argument(
        "--save-last",
        type=Path,
        default=None,
        help="Optional path to save the latest received JPEG frame.",
    )
    return parser.parse_args()


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size

    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("Socket closed while receiving frame data.")
        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)


@dataclass
class CameraFrame:
    width: int
    height: int
    frame_id: int
    timestamp_ns: int
    jpeg_bytes: bytes
    received_at: float


class CameraReceiver:
    def __init__(self, host: str, port: int, save_last: Path | None = None) -> None:
        self.host = host
        self.port = port
        self.save_last = save_last
        self._latest_frame: CameraFrame | None = None
        self._latest_image: Image.Image | None = None
        self._frame_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._server_socket: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._frames_total = 0
        self._last_stats_time = time.monotonic()
        self._last_stats_frames = 0
        self._latest_metadata: dict | None = None

    def start(self) -> None:
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind((self.host, self.port))
        self._server_socket.listen(1)
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()
        logging.info("Quest camera receiver listening on tcp://%s:%d", self.host, self.port)

    def stop(self) -> None:
        self._stop_event.set()
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except OSError:
                pass
            self._server_socket = None

        if self._accept_thread is not None:
            self._accept_thread.join(timeout=1.0)
            self._accept_thread = None

    def get_latest_image(self) -> Image.Image | None:
        with self._frame_lock:
            return self._latest_image.copy() if self._latest_image is not None else None

    def _accept_loop(self) -> None:
        assert self._server_socket is not None

        while not self._stop_event.is_set():
            try:
                client, address = self._server_socket.accept()
            except OSError:
                if self._stop_event.is_set():
                    break
                logging.exception("Accept failed.")
                continue

            logging.info("Quest camera client connected from %s:%d", address[0], address[1])
            try:
                self._handle_client(client)
            except ConnectionError as exc:
                logging.warning("Camera client disconnected: %s", exc)
            except Exception:
                logging.exception("Unexpected camera receiver error.")
            finally:
                try:
                    client.close()
                except OSError:
                    pass
                logging.info("Quest camera client closed.")

    def _handle_client(self, client: socket.socket) -> None:
        client.settimeout(5.0)

        while not self._stop_event.is_set():
            magic = struct.unpack("<I", _recv_exact(client, 4))[0]
            if magic == METADATA_MAGIC:
                header = struct.pack("<I", magic) + _recv_exact(client, METADATA_HEADER_STRUCT.size - 4)
                (
                    _magic,
                    version,
                    _reserved0,
                    _reserved1,
                    payload_size,
                ) = METADATA_HEADER_STRUCT.unpack(header)
                if version != PROTOCOL_VERSION:
                    raise ConnectionError(f"Unsupported metadata protocol version: {version}")
                payload = _recv_exact(client, payload_size)
                self._latest_metadata = json.loads(payload.decode("utf-8"))
                logging.info(
                    "camera calibration metadata received source=%s eye=%s",
                    self._latest_metadata.get("source"),
                    self._latest_metadata.get("camera_eye"),
                )
                continue

            if magic != FRAME_MAGIC:
                raise ConnectionError(f"Unexpected frame magic: 0x{magic:08X}")

            header = struct.pack("<I", magic) + _recv_exact(client, HEADER_STRUCT.size - 4)
            (
                _magic,
                version,
                _reserved0,
                width,
                height,
                _reserved1,
                _reserved2,
                frame_id,
                timestamp_ns,
                payload_size,
            ) = HEADER_STRUCT.unpack(header)
            if version != PROTOCOL_VERSION:
                raise ConnectionError(f"Unsupported protocol version: {version}")
            if payload_size <= 0:
                raise ConnectionError("Received empty JPEG payload.")

            jpeg_bytes = _recv_exact(client, payload_size)
            image = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
            frame = CameraFrame(
                width=width,
                height=height,
                frame_id=frame_id,
                timestamp_ns=timestamp_ns,
                jpeg_bytes=jpeg_bytes,
                received_at=time.monotonic(),
            )

            with self._frame_lock:
                self._latest_frame = frame
                self._latest_image = image

            self._frames_total += 1
            if self.save_last is not None:
                self.save_last.write_bytes(jpeg_bytes)

            self._log_stats(frame)

    def _log_stats(self, frame: CameraFrame) -> None:
        now = time.monotonic()
        if now - self._last_stats_time < 1.0:
            return

        frames_in_window = self._frames_total - self._last_stats_frames
        elapsed = max(now - self._last_stats_time, 1e-6)
        fps = frames_in_window / elapsed
        logging.info(
            "camera fps=%.2f latest_frame=%d size=%dx%d bytes=%d ts_ns=%d",
            fps,
            frame.frame_id,
            frame.width,
            frame.height,
            len(frame.jpeg_bytes),
            frame.timestamp_ns,
        )
        self._last_stats_time = now
        self._last_stats_frames = self._frames_total


def _run_display(receiver: CameraReceiver) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("Missing dependency. Install matplotlib to use --display.") from exc

    plt.ion()
    figure, axis = plt.subplots()
    image_artist = None

    while True:
        image = receiver.get_latest_image()
        if image is not None:
            if image_artist is None:
                image_artist = axis.imshow(image)
                axis.set_title("Quest Camera Uplink")
                axis.axis("off")
            else:
                image_artist.set_data(image)
            figure.canvas.draw_idle()

        plt.pause(0.03)


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    receiver = CameraReceiver(args.host, args.port, save_last=args.save_last)
    receiver.start()

    try:
        if args.display:
            _run_display(receiver)
        else:
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        logging.info("Shutting down quest camera receiver.")
    finally:
        receiver.stop()


if __name__ == "__main__":
    main()
