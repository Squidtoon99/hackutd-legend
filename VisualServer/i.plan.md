# i.plan.md — Python OpenCV + AprilTags AR Overlay (Mac + iPhone Continuity Camera)

## Overview
Build a pure Python app on macOS that uses iPhone Continuity Camera as a webcam, detects AprilTags (tag36h11), estimates pose using camera intrinsics and known tag size, and overlays a simple 3D cube plus a small 2D info panel with mock server data. No Swift/ARKit.

## Tech stack
- Python 3.10+
- OpenCV (opencv-python) + NumPy
- AprilTags via pupil-apriltags (macOS wheels available)
- Optional: PyYAML for loading camera calibration YAML (intrinsics)

## User flow
1. Start the app; it opens the iPhone Continuity Camera feed (select via --camera-index).
2. Each frame, detect AprilTags (family tag36h11) and get pose (R, t) using intrinsics and known tag size (meters).
3. Project a small 3D cube on the tag plane; draw axes for orientation.
4. Draw a semi-transparent 2D info panel near the tag with mock data (name, temp, Jira, uptime) keyed by tag id.
5. Smooth pose with EMA to reduce jitter; hide overlay after timeout when the tag is lost.

## Files to add
- app.py — main loop: capture, detect, pose, overlay, CLI args.
- apriltag_detector.py — AprilTag wrapper (tag36h11), returns corners, id, R, t.
- camera.py — intrinsics management (default guess or load calib/camera.yaml).
- overlay.py — 3D cube projection (cv2.projectPoints), axes, 2D info panel, EMA smoothing.
- data.py — mock ServerInfo store keyed by tag id.
- calib/camera.yaml — optional calibration file with K (fx,fy,cx,cy) and dist.
- requirements.txt — dependencies.
- README.md — setup, Continuity Camera selection, run instructions.

## CLI arguments
- --camera-index INT (default: auto search 0..5)
- --tag-size-m FLOAT (default: 0.05)
- --calib PATH (YAML with K and dist)
- --ema-alpha FLOAT (default: 0.5)

## Implementation highlights
- Camera capture
  - OpenCV capture: cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
  - If index not provided, probe 0..5 and pick the first that opens; print resolution.

- AprilTag detection
```python
from pupil_apriltags import Detector

det = Detector(
    families="tag36h11", nthreads=2, quad_decimate=2.0, quad_sigma=0.0,
    refine_edges=True, decode_sharpening=0.25
)
results = det.detect(
    gray, estimate_tag_pose=True,
    camera_params=(fx, fy, cx, cy), tag_size=tag_size_m
)
# For each result: result.tag_id, result.corners (4x2), result.pose_R (3x3), result.pose_t (3x1)
```

- Intrinsics
  - If no calib file, approximate: fx=fy=1.2*max(w,h), cx=w/2, cy=h/2; dist=zeros(5).
  - If calib provided, load K and dist from YAML.

- Pose handling + projection
```python
# R (3x3) and t (3x1) from detector → rvec for OpenCV projection
rvec, _ = cv2.Rodrigues(R)
# Define cube in tag coordinate frame (tag plane at Z=0, centered at origin)
S = tag_size_m
cube = np.float32([
    [-S/2,-S/2,0], [ S/2,-S/2,0], [ S/2, S/2,0], [-S/2, S/2,0],
    [-S/2,-S/2,S/2], [ S/2,-S/2,S/2], [ S/2, S/2,S/2], [-S/2, S/2,S/2]
])
img_pts, _ = cv2.projectPoints(cube, rvec, tvec, K, dist)
# Draw edges and axes
```

- 2D info panel
  - Use tag centroid; alpha-blended rectangle + cv2.putText lines: name, temp, Jira, uptime.

- Smoothing
  - EMA per tag id on rvec and tvec: state = a*new + (1-a)*prev.

- Mock data
```python
from dataclasses import dataclass

@dataclass
class ServerInfo:
    name: str
    tempC: int
    jira: str
    uptime: str

MOCK = {
    1: ServerInfo("Rack A12 - Srv 01", 31, "DC-1234 Open", "27d 4h"),
    2: ServerInfo("Rack A12 - Srv 02", 28, "—", "14d 2h"),
}
```

## Setup
- Create venv
- pip install -r requirements.txt
- Ensure iPhone Continuity Camera is available as a webcam device

## Running
- Example: python app.py --camera-index 0 --tag-size-m 0.05
- With calibration: python app.py --camera-index 0 --tag-size-m 0.048 --calib calib/camera.yaml

## Future improvements
- Multi-tag tracking; configurable id→server mapping file
- Replace mock store with Jira/Prometheus/NetBox clients
- Homography-warp a richer panel onto the tag plane; occlusion if depth becomes available


