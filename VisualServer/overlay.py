from typing import Dict, Tuple

import cv2
import numpy as np

from data import ServerInfo


def project_cube_points(tag_size_m: float) -> np.ndarray:
	S = float(tag_size_m)
	cube = np.float32(
		[
			[-S / 2, -S / 2, 0.0],
			[S / 2, -S / 2, 0.0],
			[S / 2, S / 2, 0.0],
			[-S / 2, S / 2, 0.0],
			[-S / 2, -S / 2, S / 2],
			[S / 2, -S / 2, S / 2],
			[S / 2, S / 2, S / 2],
			[-S / 2, S / 2, S / 2],
		]
	)
	return cube


def draw_cube(image: np.ndarray, img_pts: np.ndarray, color=(0, 200, 255)) -> None:
	pts = img_pts.reshape(-1, 2).astype(int)
	# base square
	for i in range(4):
		cv2.line(image, tuple(pts[i]), tuple(pts[(i + 1) % 4]), color, 2, cv2.LINE_AA)
	# top square
	for i in range(4, 8):
		cv2.line(image, tuple(pts[i]), tuple(pts[4 + (i + 1 - 4) % 4]), color, 2, cv2.LINE_AA)
	# verticals
	for i in range(4):
		cv2.line(image, tuple(pts[i]), tuple(pts[i + 4]), color, 2, cv2.LINE_AA)


def draw_axes(image: np.ndarray, rvec: np.ndarray, tvec: np.ndarray, K: np.ndarray, dist: np.ndarray, axis_len: float) -> None:
	axis = np.float32(
		[
			[0.0, 0.0, 0.0],
			[axis_len, 0.0, 0.0],
			[0.0, axis_len, 0.0],
			[0.0, 0.0, axis_len],
		]
	)
	img_pts, _ = cv2.projectPoints(axis, rvec, tvec, K, dist)
	o, x, y, z = img_pts.reshape(-1, 2).astype(int)
	cv2.line(image, tuple(o), tuple(x), (0, 0, 255), 2, cv2.LINE_AA)
	cv2.line(image, tuple(o), tuple(y), (0, 255, 0), 2, cv2.LINE_AA)
	cv2.line(image, tuple(o), tuple(z), (255, 0, 0), 2, cv2.LINE_AA)


def draw_info_panel(
	image: np.ndarray,
	anchor_xy: Tuple[int, int],
	info: ServerInfo,
	alpha: float = 0.6,
	scale: float = 1.0,
) -> None:
	x, y = anchor_xy
	lines = [
		info.name,
		f"Temp: {info.tempC} C",
		f"Jira: {info.jira}",
		f"Uptime: {info.uptime}",
	]
	# Scalable metrics
	font_scale = max(0.5, 0.6 * scale)
	thickness = max(1, int(round(2 * (0.6 if scale < 1.0 else scale))))
	padding = max(6, int(round(10 * scale)))
	line_h = max(18, int(round(24 * scale)))
	min_width = max(160, int(round(240 * scale)))
	width = max(min_width, max(cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0][0] for s in lines) + 2 * padding)
	height = line_h * len(lines) + 2 * padding
	# Place panel slightly above and to the right of anchor
	offset = max(12, int(round(16 * scale)))
	px = max(0, min(image.shape[1] - width - 1, x + offset))
	py = max(0, min(image.shape[0] - height - 1, y - height - offset))
	overlay = image.copy()
	cv2.rectangle(overlay, (px, py), (px + width, py + height), (30, 30, 30), -1)
	cv2.rectangle(overlay, (px, py), (px + width, py + height), (200, 200, 200), 1)
	cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)
	for i, s in enumerate(lines):
		cv2.putText(
			image,
			s,
			(px + padding, py + padding + (i + 1) * (line_h - 2)),
			cv2.FONT_HERSHEY_SIMPLEX,
			font_scale,
			(255, 255, 255),
			thickness,
			cv2.LINE_AA,
		)


class PoseFilter:
	def __init__(self, alpha: float = 0.5):
		self.alpha = float(alpha)
		self._rvecs: Dict[int, np.ndarray] = {}
		self._tvecs: Dict[int, np.ndarray] = {}

	def update(self, tag_id: int, rvec: np.ndarray, tvec: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
		if tag_id not in self._rvecs:
			self._rvecs[tag_id] = rvec.copy()
			self._tvecs[tag_id] = tvec.copy()
			return rvec, tvec
		a = self.alpha
		self._rvecs[tag_id] = a * rvec + (1.0 - a) * self._rvecs[tag_id]
		self._tvecs[tag_id] = a * tvec + (1.0 - a) * self._tvecs[tag_id]
		return self._rvecs[tag_id], self._tvecs[tag_id]


