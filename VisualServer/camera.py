from typing import List, Optional, Tuple

import cv2
import numpy as np
import yaml
import subprocess
import re


def open_camera(preferred_index: Optional[int] = None) -> Tuple[cv2.VideoCapture, int]:
	"""
	Open a camera using AVFoundation (macOS). If preferred_index is None, probe indices 0..5.
	Returns (capture, index). Raises RuntimeError if none open.
	"""
	backend = cv2.CAP_AVFOUNDATION
	indices = [preferred_index] if preferred_index is not None else list(range(6))
	last_err = None
	for idx in indices:
		try:
			cap = cv2.VideoCapture(idx, backend)
			if cap.isOpened():
				return cap, idx
			cap.release()
		except Exception as e:  # noqa: BLE001
			last_err = e
			continue
	raise RuntimeError(f"Unable to open any camera (last_err={last_err})")


def get_frame_size(cap: cv2.VideoCapture) -> Tuple[int, int]:
	width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
	height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
	if width <= 0 or height <= 0:
		# Fallback read to get shape
		ok, frame = cap.read()
		if not ok or frame is None:
			raise RuntimeError("Failed to read a frame to determine size")
		height, width = frame.shape[:2]
		return width, height
	return width, height


def approximate_intrinsics(width: int, height: int) -> Tuple[np.ndarray, np.ndarray, Tuple[float, float, float, float]]:
	"""
	Approximate camera intrinsics: fx=fy=1.2*max(w,h), principal point at center, zero distortion.
	Returns (K, dist, (fx, fy, cx, cy)).
	"""
	max_side = float(max(width, height))
	fx = fy = 1.2 * max_side
	cx = width / 2.0
	cy = height / 2.0
	K = np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float32)
	dist = np.zeros((5,), dtype=np.float32)
	return K, dist, (fx, fy, cx, cy)


def load_intrinsics_yaml(path: str) -> Tuple[np.ndarray, np.ndarray, Tuple[float, float, float, float]]:
	with open(path, "r", encoding="utf-8") as f:
		data = yaml.safe_load(f)
	K_list = data.get("K")
	dist_list = data.get("dist")
	if not K_list or len(K_list) != 9:
		raise ValueError("camera.yaml missing K with 9 entries")
	if not dist_list or len(dist_list) not in (4, 5, 8):
		raise ValueError("camera.yaml missing dist with 4/5/8 entries")
	K = np.array(K_list, dtype=np.float32).reshape(3, 3)
	dist = np.array(dist_list, dtype=np.float32).reshape(-1)
	fx = float(K[0, 0])
	fy = float(K[1, 1])
	cx = float(K[0, 2])
	cy = float(K[1, 2])
	return K, dist, (fx, fy, cx, cy)


def probe_cameras(max_index: int = 6) -> List[Tuple[int, int, int]]:
	"""
	Probe camera indices [0..max_index-1] using AVFoundation and return list of (index, width, height)
	for devices that open successfully.
	"""
	results: List[Tuple[int, int, int]] = []
	for idx in range(max_index):
		try:
			cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
			if not cap.isOpened():
				cap.release()
				continue
			ok, frame = cap.read()
			if not ok or frame is None:
				cap.release()
				continue
			h, w = frame.shape[:2]
			results.append((idx, w, h))
			cap.release()
		except Exception:  # noqa: BLE001
			continue
	return results


def list_avfoundation_devices_ffmpeg() -> List[Tuple[int, str]]:
	"""
	Use ffmpeg to list AVFoundation devices. Requires ffmpeg on PATH (opencv-python bundles ffmpeg
	for decoding, but not the CLI tool; users may need Homebrew ffmpeg).
	Returns list of (index, name). If ffmpeg is missing, returns [].
	"""
	try:
		# ffmpeg -f avfoundation -list_devices true -i ""
		proc = subprocess.run(
			["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
			stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT,
			check=False,
			text=True,
		)
		out = proc.stdout
	except Exception:
		return []

	devs: List[Tuple[int, str]] = []
	pat = re.compile(r"\[\d+\]\s+(.*)")  # lines like: [0] FaceTime HD Camera
	for line in out.splitlines():
		line = line.strip()
		if "AVFoundation video devices" in line:
			collect = True
			continue
		if line.startswith("[") and "]" in line:
			# Try to parse "[index] name"
			try:
				idx_str = line.split("]")[0].strip("[")
				idx = int(idx_str)
				name = line.split("]")[1].strip()
				devs.append((idx, name))
			except Exception:
				continue
	return devs


def open_ffmpeg_avfoundation_by_index(idx: int) -> Optional[cv2.VideoCapture]:
	"""
	Open AVFoundation device via FFmpeg backend using device index.
	"""
	url = f"avfoundation:{idx}"
	cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
	if cap.isOpened():
		return cap
	cap.release()
	return None


def open_ffmpeg_avfoundation_by_name(name: str) -> Optional[cv2.VideoCapture]:
	"""
	Open AVFoundation device via FFmpeg backend using device name (e.g., 'Continuity Camera').
	"""
	# Try exact name
	url = f"avfoundation:{name}"
	cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
	if cap.isOpened():
		return cap
	# Try quoted name (some builds require quotes to be part of the url)
	url2 = f'avfoundation:"{name}"'
	cap = cv2.VideoCapture(url2, cv2.CAP_FFMPEG)
	if cap.isOpened():
		return cap
	return None



