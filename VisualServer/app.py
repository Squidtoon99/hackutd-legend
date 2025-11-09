import argparse
import time
from typing import Optional, Tuple

import cv2
import numpy as np

from apriltag_detector import AprilTagDetector
from camera import (
	approximate_intrinsics,
	get_frame_size,
	load_intrinsics_yaml,
	open_camera,
	probe_cameras,
	list_avfoundation_devices_ffmpeg,
	open_ffmpeg_avfoundation_by_index,
)
from data import MOCK_SERVERS
from overlay import PoseFilter, draw_axes, draw_cube, draw_info_panel, project_cube_points


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description="AprilTags AR Overlay (macOS + Continuity Camera)")
	parser.add_argument("--camera-index", type=int, default=None, help="Webcam index; omit to auto-probe 0..5")
	parser.add_argument("--tag-size-m", type=float, default=0.05, help="Physical AprilTag size (edge length in meters)")
	parser.add_argument("--calib", type=str, default=None, help="Path to calib/camera.yaml with K and dist")
	parser.add_argument("--ema-alpha", type=float, default=0.5, help="Smoothing factor (0..1), higher = snappier")
	parser.add_argument("--list-cameras", action="store_true", help="List available camera indices and exit")
	parser.add_argument("--ip-url", type=str, default=None, help="Open IP/RTSP/HTTP video stream instead of webcam index")
	parser.add_argument("--use-ffmpeg-avf", action="store_true", help="Use FFmpeg avfoundation device open (for Continuity Camera)")
	parser.add_argument("--avf-index", type=int, default=None, help="AVFoundation device index for FFmpeg backend")
	parser.add_argument("--avf-name", type=str, default=None, help="AVFoundation device name for FFmpeg backend (e.g., 'Continuity Camera')")
	parser.add_argument("--panel-scale", type=float, default=1.6, help="Scale factor for info panel size (default 1.6)")
	return parser.parse_args()


def main() -> None:
	args = parse_args()

	if args.list_cameras:
		results = probe_cameras(10)
		if not results:
			print("No cameras found. Ensure Continuity Camera is active and try again.")
		else:
			print("Available cameras (OpenCV AVFoundation):")
		for idx, w, h in results:
			print(f"  index={idx}  approx_res={w}x{h}")
		avf = list_avfoundation_devices_ffmpeg()
		if avf:
			print("\nAVFoundation devices via ffmpeg (may include Continuity Camera):")
			for idx, name in avf:
				print(f"  avf-index={idx}  name={name}")
			print("\nRun with: python app.py --use-ffmpeg-avf --avf-index <idx> --tag-size-m 0.05")
		else:
			print("\nTip: Install ffmpeg (brew install ffmpeg) to list avfoundation devices by name.")
		print("\nRun with: python app.py --camera-index <index> --tag-size-m 0.05")
		return

	# Open capture (IP stream or local camera)
	cap = None
	cam_idx: Optional[int] = None
	if args.ip_url:
		print(f"[INFO] Opening IP camera URL: {args.ip_url}")
		cap = cv2.VideoCapture(args.ip_url)
		if not cap.isOpened():
			raise RuntimeError(f"Failed to open IP camera URL: {args.ip_url}")
	elif args.use_ffmpeg_avf:
		if args.avf_index is None and not args.avf_name:
			avf = list_avfoundation_devices_ffmpeg()
			if not avf:
				raise RuntimeError("No AVFoundation devices via ffmpeg. Install ffmpeg and ensure Continuity Camera is active.")
			print("AVFoundation devices via ffmpeg:")
			for idx, name in avf:
				print(f"  avf-index={idx}  name={name}")
			raise RuntimeError("Specify --avf-index or --avf-name to select device.")
		if args.avf_name:
			print(f"[INFO] Opening AVFoundation device via ffmpeg by name: {args.avf_name}")
			cap = open_ffmpeg_avfoundation_by_index(args.avf_index) if args.avf_index is not None else None
			if cap is None:
				from camera import open_ffmpeg_avfoundation_by_name
				cap = open_ffmpeg_avfoundation_by_name(args.avf_name)
		else:
			print(f"[INFO] Opening AVFoundation device via ffmpeg: index {args.avf_index}")
			cap = open_ffmpeg_avfoundation_by_index(args.avf_index)
		if cap is None:
			raise RuntimeError(f"Failed to open ffmpeg avfoundation device (index={args.avf_index}, name={args.avf_name})")
	else:
		cap, cam_idx = open_camera(args.camera_index)
		print(f"[INFO] Opened camera index: {cam_idx}")
	width, height = get_frame_size(cap)
	print(f"[INFO] Frame size: {width}x{height}")

	# Intrinsics
	if args.calib:
		K, dist, (fx, fy, cx, cy) = load_intrinsics_yaml(args.calib)
		print("[INFO] Loaded intrinsics from YAML")
	else:
		K, dist, (fx, fy, cx, cy) = approximate_intrinsics(width, height)
		print("[INFO] Using approximate intrinsics")

	# AprilTag detector
	detector = AprilTagDetector(
		tag_size_m=args.tag_size_m,
		camera_params=(fx, fy, cx, cy),
		nthreads=2,
		quad_decimate=2.0,
		quad_sigma=0.0,
		refine_edges=True,
		decode_sharpening=0.25,
	)

	# Overlay helpers
	cube_3d = project_cube_points(args.tag_size_m)
	pose_filter = PoseFilter(alpha=args.ema_alpha)

	prev_time = time.time()
	fps = 0.0

	while True:
		ok, frame = cap.read()
		if not ok or frame is None:
			print("[WARN] Failed to read frame")
			break

		gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
		detections = detector.detect(gray)

		# FPS estimate
		now = time.time()
		delta = now - prev_time
		prev_time = now
		if delta > 0:
			fps = 0.9 * fps + 0.1 * (1.0 / delta) if fps > 0 else 1.0 / delta

		# Render for each detection
		for det in detections:
			# Smooth pose
			rvec_s, tvec_s = pose_filter.update(det.tag_id, det.rvec, det.tvec)

			# Project cube
			img_pts, _ = cv2.projectPoints(cube_3d, rvec_s, tvec_s, K, dist)
			draw_cube(frame, img_pts)

			# Axes
			draw_axes(frame, rvec_s, tvec_s, K, dist, axis_len=args.tag_size_m * 0.75)

			# Info panel near centroid
			info = MOCK_SERVERS.get(det.tag_id)
			if info is None:
				# Fallback info if unknown id
				from data import ServerInfo
				info = ServerInfo(name=f"Tag {det.tag_id}", tempC=0, jira="N/A", uptime="N/A")
			center_xy = (int(det.center[0]), int(det.center[1]))
			draw_info_panel(frame, center_xy, info, scale=args.panel_scale)

			# Draw corner outline
			c = det.corners.astype(int)
			for i in range(4):
				cv2.line(frame, tuple(c[i]), tuple(c[(i + 1) % 4]), (0, 255, 255), 1, cv2.LINE_AA)
			cv2.circle(frame, center_xy, 3, (0, 255, 0), -1, cv2.LINE_AA)
			cv2.putText(
				frame,
				f"id={det.tag_id}",
				(center_xy[0] + 8, center_xy[1] - 8),
				cv2.FONT_HERSHEY_SIMPLEX,
				0.5,
				(0, 255, 0),
				1,
				cv2.LINE_AA,
			)

		# HUD
		cv2.putText(
			frame,
			f"FPS: {fps:.1f}",
			(10, 20),
			cv2.FONT_HERSHEY_SIMPLEX,
			0.6,
			(255, 255, 255),
			1,
			cv2.LINE_AA,
		)
		cv2.putText(
			frame,
			"Press 'q' to quit",
			(10, 42),
			cv2.FONT_HERSHEY_SIMPLEX,
			0.5,
			(200, 200, 200),
			1,
			cv2.LINE_AA,
		)

		cv2.imshow("AprilTags AR Overlay", frame)
		key = cv2.waitKey(1) & 0xFF
		if key == ord("q"):
			break

	cap.release()
	cv2.destroyAllWindows()


if __name__ == "__main__":
	main()


