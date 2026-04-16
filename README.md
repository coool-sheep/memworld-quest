<h3 align="center">
    Meta Quest VR App for tracking and streaming video, hand and wrist landmark telemetry.
  </h3>
</div>
<p align="center">


**Hand Tracking Streamer** is a lightweight hand telemetry utility that turns a Meta Quest headset into a precision controller for robotics teleoperation and motion capture. Built on the Meta Interaction SDK, it streams 21-landmark hand data and 6-DoF wrist pose to a PC in real time over Wi-Fi using UDP for ultra-low latency or TCP for reliable data logging. The app supports left, right, or dual-hand modes with in-headset configuration, and includes a live log console and phantom hand visualization for debugging. Data is sent as structured packets of joint positions and orientations in Unity world space, making it suitable for robot control, imitation learning, and gesture-based prototyping.

## Camera Uplink Status

This repository now includes a Quest-to-PC camera uplink path designed for **fixed TCP ports** and **USB wired use via `adb reverse`**:

- Android manifest declares `horizonos.permission.HEADSET_CAMERA`.
- Stream metadata (`frame id` and monotonic `timestamp_ns`) is enabled by default for hand and head packets.
- `QuestCameraCapture` reads Quest passthrough camera textures through Meta PCA / MRUK.
- `QuestVideoSender` sends each frame as a JPEG payload over a dedicated TCP socket.
- `scripts/quest_camera_receiver.py` receives and optionally previews that JPEG stream on the PC.

>[!IMPORTANT]
> To access Quest 3 / 3S camera textures, upgrade to a Meta MR Utility Kit (MRUK) version that provides `PassthroughCameraAccess`, enable `requestPassthroughCameraAccessPermissionOnStartup`, and build on-device. Meta's official PCA samples currently require Quest 3 / 3S, Horizon OS v74+, and MRUK v81+.

### Camera Uplink Quick Start

1. Quest Side: install adb in windows first, then install apk in your quest.

```bash
adb install -r "path_to_HTVS.apk"
```

2. Create the USB reverse mappings:

```bash
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8765 tcp:8765
```

3. In the Quest app, choose `TCP Wired`, set the IP to `127.0.0.1`, keep the hand port at `8000`, and enable `Camera Output`.

4. Start recording:

```bash
python ./scripts/record_quest_dataset.py --name your_dataset_name --output-root ./data --fps 30
```

If you want to manually split one recording into multiple segments, enable segmentation and use the preview window:

```bash
python ./scripts/record_quest_dataset.py --name your_dataset_name --output-root ./data --fps 30 --enable-segmentation
```

While recording:

- press `n` in the preview window to close the current segment and start the next one
- press `q` to stop recording

When segmentation is enabled, the dataset directory also includes `segments.json`.

To export `seg1 + segN` combinations after recording:

```bash
python ./scripts/export_stage_combinations.py --name your_dataset_name --output-root ./data
```

### Segmented Recording Workflow

如果一整段录制里包含多个阶段，比如 `A -> B -> C -> D`，就用分段模式。

开始录制：

```bash
python ./scripts/record_quest_dataset.py --name demo_segments --output-root ./data --fps 30 --enable-segmentation
```

录制时只记这几件事：

- 第一个真正录到的相机帧会自动开始 `seg1`
- 每按一次 `n`，结束当前段，下一段从下一帧开始
- 最后按 `q` 停止录制，最后一段会自动封口

录完以后原始目录大概是：

```text
data/demo_segments/
  camera.mp4
  camera_frames.parquet
  aligned_frames.parquet
  telemetry_raw.parquet
  session.json
  segments.json
```

其中 `segments.json` 记录每一段的起止帧和时间戳。

然后导出组合：

```bash
python ./scripts/export_stage_combinations.py --name demo_segments --output-root ./data
```

导出后会生成：

```text
data/demo_segments/exports/
  seg1_seg2/
    camera.mp4
    aligned_frames.parquet
    session.json
    export_manifest.json
  seg1_seg3/
    camera.mp4
    aligned_frames.parquet
    session.json
    export_manifest.json
  seg1_seg4/
    camera.mp4
    aligned_frames.parquet
    session.json
    export_manifest.json
```

意思就是：

- `seg1` is always the first recorded segment
- exports are generated as `seg1 + segN`
- exported `aligned_frames.parquet` is rebuilt to match the exported video frame order
- exported folders now include `camera.mp4 + session.json + aligned_frames.parquet`
- if you only recorded two segments, only `seg1_seg2` is generated

5. vissualize dataset:

```bash
python ./scripts/reproject_quest_dataset.py --name your_dataset_name
```


## Deployment


### Local Builds

Please directly upload `hand_tracking_video_streamer.apk` via ADB to your device.

>[!NOTE]
>Before direct upload, make sure your device is set to [developer mode](https://developers.meta.com/horizon/documentation/native/android/mobile-device-setup/), and allow USB connection. This app is built and tested on Unity 6000.4.1f1

## Data Streaming

See [CONNECTIONS](CONNECTIONS.md) page for detailed documentation on hand-data connections, the fixed-port camera uplink, and packet formats. 

### Quick Start
Not ready to integrate into your system yet? Check out the simple socket and the visualizer script provided under [/scripts](/scripts) for quickly testing data streamed from your device.

<details>
<summary>Click to see visualizer in action</summary>

Install dependencies, connect HTS, and simply run:

```python
python ./scripts/visualizer.py --protocol [YOUR PROTOCOL] --host [YOUR HOST IP] --port [YOUR PORT] --show-fingers
```
    
![visualizer](https://github.com/user-attachments/assets/431c994a-9287-4641-acb3-22e96c83b925)

</details>

## Python SDK

For integrating HTS data into your own pipelines, use the official [Python SDK](https://github.com/wengmister/hand-tracking-sdk). It provides typed data structures, parsers for the HTS packet format, and utilities for real-time visualization and logging, so you can go from streamed packets to usable hand pose data quickly. The package is published on [PyPI](https://pypi.org/project/hand-tracking-sdk/); see the [documentation](https://hand-tracking-sdk.readthedocs.io/en/latest/) for API details and examples.

```bash
# if using uv
uv add hand-tracking-sdk
# or just
uv init && uv venv && uv sync

# or install via pip
pip install hand-tracking-sdk
```

## Demo

## Contact

For support or privacy inquiries related to Hand Tracking Streamer, please email: **gboxer.boxer@gmail.com**


## Acknowledgements

This project uses [Hand Tracking Streamer](https://github.com/wengmister/hand-tracking-streamer) for [insert specific use case here, e.g., VR hand motion capture]. We would like to thank the author for their open-source contribution.

If you use this project in your research or work, please also cite the original Hand Tracking Streamer:

**Plain Text:**
> Weng, Z. K. (2026). Hand Tracking Streamer: Meta Quest VR App for Motion Capture and Teleoperation. GitHub. https://github.com/wengmister/hand-tracking-streamer

**BibTeX:**
```bibtex
@software{weng2026hts,
      author={Weng, Zhengyang K.},
      title={Hand Tracking Streamer: Meta Quest VR App for Motion Capture and Teleoperation},
      url={https://github.com/wengmister/hand-tracking-streamer},
      year={2026}
}
```

## License
Apache-2.0
