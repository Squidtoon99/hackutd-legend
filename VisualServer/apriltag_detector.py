from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from pupil_apriltags import Detector


class AprilTagDetection:
	def __init__(self, tag_id: int, corners: np.ndarray, rvec: np.ndarray, tvec: np.ndarray, center: Tuple[float, float]):
		self.tag_id = tag_id
		self.corners = corners  # shape (4, 2)
		self.rvec = rvec  # shape (3, 1)
		self.tvec = tvec  # shape (3, 1)
		self.center = center


class AprilTagDetector:
	def __init__(
		self,
		tag_size_m: float,
		camera_params: Tuple[float, float, float, float],
		nthreads: int = 2,
		quad_decimate: float = 2.0,
		quad_sigma: float = 0.0,
		refine_edges: bool = True,
		decode_sharpening: float = 0.25,
	):
		self.tag_size_m = float(tag_size_m)
		self.fx, self.fy, self.cx, self.cy = camera_params
		self._detector = Detector(
			families="tag36h11",
			nthreads=nthreads,
			quad_decimate=quad_decimate,
			quad_sigma=quad_sigma,
			refine_edges=refine_edges,
			decode_sharpening=decode_sharpening,
		)

	def detect(self, gray: np.ndarray) -> List[AprilTagDetection]:
		results = self._detector.detect(
			gray,
			estimate_tag_pose=True,
			camera_params=(self.fx, self.fy, self.cx, self.cy),
			tag_size=self.tag_size_m,
		)
		detections: List[AprilTagDetection] = []
		for res in results:
			# res.pose_R (3x3), res.pose_t (3x1)
			R: np.ndarray = res.pose_R
			t: np.ndarray = res.pose_t
			rvec, _ = cv2.Rodrigues(R)
			corners = np.asarray(res.corners, dtype=np.float32)  # (4,2)
			center = (float(np.mean(corners[:, 0])), float(np.mean(corners[:, 1])))
			detections.append(
				AprilTagDetection(
					tag_id=int(res.tag_id),
					corners=corners,
					rvec=rvec.astype(np.float32),
					tvec=t.astype(np.float32),
					center=center,
				)
			)
		return detections


