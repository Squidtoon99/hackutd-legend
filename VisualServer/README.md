# Python OpenCV + AprilTags AR Overlay (macOS + iPhone Continuity Camera)

An MVP that:
- Captures video from iPhone Continuity Camera on macOS
- Detects AprilTags (tag36h11) with `pupil-apriltags`
- Estimates pose using camera intrinsics and known tag size
- Overlays a 3D cube and a small 2D info panel with mock server data

## Prerequisites
- macOS with Continuity Camera enabled (System Settings → General → AirDrop & Handoff)
- Python 3.10+

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
python app.py --camera-index 0 --tag-size-m 0.05
```

List available cameras (OpenCV indices and, if ffmpeg is installed, AVFoundation devices which may include Continuity Camera):
```bash
python app.py --list-cameras
```
If Continuity Camera appears under the AVFoundation section, launch with ffmpeg avfoundation:
```bash
python app.py --use-ffmpeg-avf --avf-index <idx> --tag-size-m 0.05
```
Or open by name (exact match, e.g., Continuity Camera):
```bash
python app.py --use-ffmpeg-avf --avf-name "Continuity Camera" --tag-size-m 0.05
```
Otherwise use the OpenCV index:
```bash
python app.py --camera-index <index> --tag-size-m 0.05
```

Or use an IP camera app on the iPhone (RTSP/HTTP/MJPEG URL):
```bash
python app.py --ip-url "http://<phone-ip>:<port>/video" --tag-size-m 0.05
```

Flags:
- `--camera-index` INT: webcam index; omit to auto-probe 0..5
- `--ip-url` URL: open an IP/RTSP/HTTP stream instead of a local webcam
- `--use-ffmpeg-avf`: open AVFoundation device via ffmpeg (helps with Continuity Camera)
- `--avf-index` INT: AVFoundation device index (from `--list-cameras` ffmpeg section)
- `--avf-name` STR: AVFoundation device name (e.g., "Continuity Camera")
- `--panel-scale` FLOAT: scale factor for info panel size (default 1.6)
- `--tag-size-m` FLOAT: physical tag size in meters (edge length)
- `--calib` PATH: YAML with camera intrinsics/distortion (`calib/camera.yaml`)
- `--ema-alpha` FLOAT: smoothing factor (0..1), default 0.5

Example with calibration:
```bash
python app.py --camera-index 0 --tag-size-m 0.048 --calib calib/camera.yaml
```

## Calibration file format (`calib/camera.yaml`)
```yaml
K: [fx, 0, cx, 0, fy, cy, 0, 0, 1]
dist: [k1, k2, p1, p2, k3]
```

## Notes
- Use AprilTag family: `tag36h11`
- Press `q` to quit
- If pose feels off, adjust `--tag-size-m` or provide calibration


