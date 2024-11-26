import cv2
import mediapipe as mp
import asyncio
import math
from mediapipe.framework.formats import landmark_pb2

class Tool:
    def __init__(self, name, description, function):
        self.name = name
        self.description = description
        self.function = function

class PoseEstimator(Tool):
    def __init__(self, stream):
        self.stream = stream
        self.name = "estimate_pose"
        self.description = {
            "type": "function",
            "name": "estimate_pose",
            "description": "Estimates the farmer's pose and check whether the farmer has fallen or not using a webcam feed in real-time",
            "parameters": {},
        }
        self.function = self.get_current_pose
        self.pose = mp.solutions.pose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self.mp_drawing = mp.solutions.drawing_utils
        self.fall_detected = False
        self.latest_position = None
        asyncio.create_task(self.estimate_pose())

    async def estimate_pose(self):
        """
        Continuously captures frames from the webcam and processes them to detect and display pose landmarks.
        """
        while True:
            start_time = asyncio.get_event_loop().time()
            ret, frame = await asyncio.to_thread(self.stream.read)
            if not ret:
                print("Unable to read frame from the video stream.")
                break

            image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.pose.process(image)

            if results.pose_landmarks:
                self.mp_drawing.draw_landmarks(
                    image, results.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=self.mp_drawing.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2),
                    connection_drawing_spec=self.mp_drawing.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2)
                )
                self.fall_detected = self.detect_fall(results.pose_landmarks)

                self.latest_position = self.calculate_farmer_position(results.pose_landmarks)

            # Maintain frame rate
            elapsed_time = asyncio.get_event_loop().time() - start_time
            await asyncio.sleep(max(0, (1/30) - elapsed_time))  # Assuming 30 fps

            print("-------")

    async def get_current_pose(self):
        """
        Returns the current pose information, including fall detection status and farmer's position.
        """
        return {
            "fall_detected": self.fall_detected,
            "direction": self.latest_position.get("direction", "Unknown") if self.latest_position else "Unknown",
            "distance": self.latest_position.get("distance", None) if self.latest_position else None,
        }

    def calculate_farmer_position(self, landmarks):
        """
        Calculates the direction and distance for the farmer's pose using landmarks.
        """
        if landmarks is None:
            return None

        try:
            # Get relevant landmarks
            left_shoulder = landmarks.landmark[mp.solutions.pose.PoseLandmark.LEFT_SHOULDER]
            right_shoulder = landmarks.landmark[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER]
            left_hip = landmarks.landmark[mp.solutions.pose.PoseLandmark.LEFT_HIP]
            right_hip = landmarks.landmark[mp.solutions.pose.PoseLandmark.RIGHT_HIP]
            world_landmarks = self.pose.process(cv2.cvtColor(self.stream.read()[1], cv2.COLOR_BGR2RGB)).pose_world_landmarks

            hip_center = (left_hip.x + right_hip.x) / 2
            hip_center = hip_center * 2 - 1

            # Calculate the shoulder-to-shoulder distance in world coordinates
            shoulder_distance_world = None
            if world_landmarks:
                left_shoulder_world = world_landmarks.landmark[mp.solutions.pose.PoseLandmark.LEFT_SHOULDER]
                right_shoulder_world = world_landmarks.landmark[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER]
                if left_shoulder_world is None or right_shoulder_world is None:
                    return None
                shoulder_distance_world = math.sqrt(
                    (left_shoulder_world.x - right_shoulder_world.x) ** 2 +
                    (left_shoulder_world.y - right_shoulder_world.y) ** 2
                )
            else:
                return None

            # 2D screen coordinate distance
            shoulder_distance_pixel = math.sqrt(
                (left_shoulder.x - right_shoulder.x) ** 2 +
                (left_shoulder.y - right_shoulder.y) ** 2
            )

            # Compute actual distance using the focal length scaling approach
            focal_length = 0.75  # Replace with actual focal length if available
            actual_shoulder_distance = (shoulder_distance_world * focal_length) / shoulder_distance_pixel if shoulder_distance_pixel > 0 else None

            return {
                "direction": hip_center,
                "distance": actual_shoulder_distance,
            }
        except IndexError as e:
            print(f"Failed to calculate farmer position: {e}")
            return None


    def calculate_farmer_position_(self, landmarks):
        """
        Calculates the direction and distance for the farmer's pose.
        """
        if landmarks is None:
            return None

        try:
            # Get relevant landmarks
            left_hip = landmarks.landmark[mp.solutions.pose.PoseLandmark.LEFT_HIP]
            right_hip = landmarks.landmark[mp.solutions.pose.PoseLandmark.RIGHT_HIP]

            # Calculate the distance between hips
            hip_distance = abs(left_hip.x - right_hip.x)

            # Determine direction (left, center, right)
            hip_center = (left_hip.x + right_hip.x) / 2
            if hip_center < 0.4:
                direction = "Left"
            elif hip_center > 0.6:
                direction = "Right"
            else:
                direction = "Center"

            return {
                "direction": direction,
                "distance": hip_distance,
            }
        except IndexError as e:
            print(f"Failed to calculate farmer position: {e}")
            return None

    def detect_fall(self, landmarks):
        if landmarks is None:
            return False

        nose = landmarks.landmark[mp.solutions.pose.PoseLandmark.NOSE]
        left_hip = landmarks.landmark[mp.solutions.pose.PoseLandmark.LEFT_HIP]
        right_hip = landmarks.landmark[mp.solutions.pose.PoseLandmark.RIGHT_HIP]

        # Assume fall if the nose's y-coordinate is not significantly higher than the hips'
        if nose.y > (left_hip.y + right_hip.y) / 2:
            return True
        return False


    def emphasize_landmarks(self, image, landmarks):
        if landmarks is None:
            return

        try:
            nose = landmarks.landmark[mp.solutions.pose.PoseLandmark.NOSE]
            left_hip = landmarks.landmark[mp.solutions.pose.PoseLandmark.LEFT_HIP]
            right_hip = landmarks.landmark[mp.solutions.pose.PoseLandmark.RIGHT_HIP]
        except IndexError as e:
            print(f"Failed to access landmark: {e}")
            return

        emphasized_drawing_spec = {
            mp.solutions.pose.PoseLandmark.NOSE.value: self.mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=8, circle_radius=10),
            mp.solutions.pose.PoseLandmark.LEFT_HIP.value: self.mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=8, circle_radius=10),
            mp.solutions.pose.PoseLandmark.RIGHT_HIP.value: self.mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=8, circle_radius=10)
        }

        landmark_drawing_spec = {i: self.mp_drawing.DrawingSpec() for i in range(len(landmarks.landmark))}
        landmark_drawing_spec.update(emphasized_drawing_spec)

        self.mp_drawing.draw_landmarks(
            image,
            landmark_list=landmarks,
            connections=[],
            landmark_drawing_spec=landmark_drawing_spec
        )

    def create_custom_landmark_list(self, full_landmarks):
        # 새로운 랜드마크 리스트 생성
        new_landmarks = landmark_pb2.NormalizedLandmarkList()

        # 강조하고자 하는 랜드마크 인덱스: 코, 왼쪽 엉덩이, 오른쪽 엉덩이
        indices_to_include = [
            mp.solutions.pose.PoseLandmark.NOSE.value,
            mp.solutions.pose.PoseLandmark.LEFT_HIP.value,
            mp.solutions.pose.PoseLandmark.RIGHT_HIP.value
        ]

        for idx in indices_to_include:
            new_landmarks.landmark.add().CopyFrom(full_landmarks.landmark[idx])

        return new_landmarks


async def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Error opening video stream.")
    else:
        pose_estimator = PoseEstimator(cap)
        try:
            while True:
                await asyncio.sleep(1)
                pose_info = await pose_estimator.get_current_pose()
                if pose_info:
                    print(f"Fall detected: {pose_info['fall_detected']}")
                    print(f"Direction: {pose_info['direction']}")
                    print(f"Distance: {pose_info['distance']}")
        except KeyboardInterrupt:
            print("Stopping...")

    cap.release()


# Run the asyncio event loop
if __name__ == "__main__":
    asyncio.run(main())
