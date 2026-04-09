# Connecting and Streaming Data from HTS

This document describes how Hand Tracking Streamer (HTS) streams hand and wrist data, and how to connect to it over UDP and TCP. It also covers the Quest camera uplink path for Quest 3 / 3S.

## Data format

HTS uses the OpenXR hand skeleton rig. Full details can be found in the [Meta documentation](https://developers.meta.com/horizon/documentation/unity/unity-handtracking-interactions/).


<img width="1999" height="951" alt="OXR Hand" src="https://github.com/user-attachments/assets/b964ca21-3cd6-44c7-b225-be503ed17a65" />


The full OpenXR hand skeleton has 29 joints, but many of them are static (palm, metacarpals, etc.) and are not streamed to save bandwidth. HTS sends the wrist plus 21 tracked joints per hand.

Tracked joint indices:

```text
[OpenXR index // streamed index: joint name]
1,  // 0: Wrist
2,  // 1: ThumbMetacarpal
3,  // 2: ThumbProximal
4,  // 3: ThumbDistal
5,  // 4: ThumbTip
7,  // 5: IndexProximal
8,  // 6: IndexIntermediate
9,  // 7: IndexDistal
10, // 8: IndexTip
12, // 9: MiddleProximal
13, // 10: MiddleIntermediate
14, // 11: MiddleDistal
15, // 12: MiddleTip
17, // 13: RingProximal
18, // 14: RingIntermediate
19, // 15: RingDistal
20, // 16: RingTip
22, // 17: LittleProximal
23, // 18: LittleIntermediate
24, // 19: LittleDistal
25  // 20: LittleTip
```

Tracked data are streamed as UTF‑8 CSV lines, with a leading label indicating side and type:

```text
Right wrist:, 0.2502, 1.0635, 0.2540, 0.194, -0.116, 0.094, -0.970
Right landmarks:, 0.0000, 0.0000, 0.0000, -0.0275, -0.0197, 0.0362, -0.0438, -0.0335, 0.0608, -0.0418, -0.0480, 0.0913, -0.0329, -0.0595, 0.1111, -0.0236, -0.0073, 0.0960, -0.0179, -0.0226, 0.1302, -0.0150, -0.0428, 0.1435, -0.0116, -0.0633, 0.1518, -0.0017, -0.0025, 0.0956, 0.0054, -0.0226, 0.1329, 0.0081, -0.0456, 0.1478, 0.0100, -0.0680, 0.1589, 0.0175, -0.0065, 0.0887, 0.0252, -0.0222, 0.1236, 0.0279, -0.0407, 0.1424, 0.0282, -0.0595, 0.1580, 0.0230, -0.0094, 0.0341, 0.0351, -0.0137, 0.0779, 0.0433, -0.0227, 0.1061, 0.0477, -0.0342, 0.1223
```

- `Right wrist:`: 7 floats → `x, y, z, qx, qy, qz, qw`.
- `Right landmarks:`: 63 floats → `[x, y, z] * 21` in the joint order listed above.

HTS can also prepend stream metadata to labels:

```text
Right wrist | f = 123 | t = 4567890123456:, 0.2502, 1.0635, 0.2540, 0.194, -0.116, 0.094, -0.970
Right landmarks | f = 123 | t = 4567890123456:, 0.0000, 0.0000, 0.0000, ...
Head pose | f = 77 | t = 4567890123999:, 0.0312, 1.5320, -0.1421, 0.002, -0.701, 0.001, 0.713
```

- `f`: monotonically increasing frame id generated on-device per stream source.
- `t`: monotonic headset timestamp in nanoseconds generated on-device at send time.
- Existing parsers should treat the metadata as part of the text label and continue reading numeric payload fields after the first comma.

>[!IMPORTANT]
> Data streamed from HTS follows Unity's left-hand coordinate convention. For most applications, you will want to flip the incoming data's Y-axis for the right-hand coordinate convention.

## UDP connection

HTS can stream data via **wireless** UDP to a host on the same network as the Quest headset.

- Default target: `255.255.255.255:9000` (broadcast).
- You can change the target IP and port from the in‑game/network configuration menu.

>[!IMPORTANT] 
>Network Performance Notice UDP streaming depends heavily on your local network conditions. Specifically, Wi-Fi networks with high DTIM intervals may cause message batching (latency spikes) due to headset power-saving features (see Issue [#4](https://github.com/wengmister/hand-tracking-streamer/issues/4)).    
>For the more reliable performance, consider using the wired/wireless TCP connection.

## TCP connection - Wired

HTS can stream data via **wired** TCP using ADB. Connect your Quest to your machine with a data‑capable USB‑C cable.

- Default target: `localhost:8000` via ADB reverse loopback.

>[!NOTE]
> TCP streaming over USB generally provides the most consistent and reliable performance. In practice, HTS over TCP tops out at around 70 Hz Quest hand tracking frequency.

Set up the TCP reverse mapping before starting streaming from the HTS app:

```bash
adb reverse tcp:8000 tcp:8000
```

You can verify that the reverse rule is active with:

```bash
adb reverse --list
```

## TCP connection - Wireless

HTS can also stream data via **Wireless** TCP to a host on the same network as the Quest headset.

- Default target: `192.168.1.1:9000`
- You will need to identify your host's local IPv4 address for connection in HTS

Set up TCP server before starting streaming from the HTS app. Minimal example provided in `.\scripts\sockets.py`

## Camera uplink - Fixed TCP port

Quest camera uplink uses a **separate fixed TCP port** from the hand telemetry stream. This path is intended for Quest 3 / 3S passthrough camera access and works especially well over **USB wired** with `adb reverse`.

- Recommended hand-data port: `8000`
- Recommended camera port: `8765`
- Recommended Quest-side IP for USB wired: `127.0.0.1`

### USB wired quick start

Start the PC listeners first:

```bash
python ./scripts/sockets.py --protocol tcp --host 127.0.0.1 --port 8000
python ./scripts/quest_camera_receiver.py --host 127.0.0.1 --port 8765 --display
```

Create the ADB reverse mappings:

```bash
adb reverse tcp:8000 tcp:8000
adb reverse tcp:8765 tcp:8765
```

Then in the Quest app:

1. Select `TCP Wired`
2. Set IP to `127.0.0.1`
3. Set the hand stream port to `8000`
4. Enable `Camera Uplink`
5. Keep `Video Stream` disabled unless you also want the separate host-to-Quest display path

### Camera frame packet format

Each camera frame is sent as:

1. A fixed-size binary header
2. A JPEG payload

Header layout (`little-endian`, 28 bytes total):

```text
uint32 magic         = 0x4D414351   // "QCAM"
uint8  version       = 1
uint8  reserved0
uint16 width
uint16 height
uint8  reserved1
uint8  reserved2
uint32 frame_id
uint64 timestamp_ns
uint32 payload_size
```

The header is immediately followed by `payload_size` bytes containing one JPEG image.

### PC receiver helper

The repo includes `.\scripts\quest_camera_receiver.py`, which:

- listens on a fixed TCP port
- parses the binary header above
- decodes the JPEG payload
- can preview frames with `--display`
- can save the latest frame with `--save-last path/to/frame.jpg`


## Troubleshooting

1. Have you enabled "Allow USB connection" on your Meta Quest?
   - Verify with `adb devices`. You should see your headset listed.
2. Make sure your firewall allows inbound traffic on the UDP/TCP port you are using.
3. For camera uplink on Quest 3 / 3S, make sure your app has `horizonos.permission.HEADSET_CAMERA`, that your project is upgraded to a Meta MR Utility Kit version with `PassthroughCameraAccess`, and that `requestPassthroughCameraAccessPermissionOnStartup` is enabled in the Oculus settings asset.
4. If hand streaming works but camera uplink fails over USB, verify both reverse rules exist:

```bash
adb reverse --list
```

You should see both `tcp:8000` and `tcp:8765`.


