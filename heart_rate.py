import cv2
import mediapipe as mp
import numpy as np
from scipy.fft import fft
import time
import logging
import asyncio


class Tool:
    def __init__(self, name, description, function):
        self.name = name
        self.description = description
        self.function = function

class HeartRateMonitor(Tool):
    def __init__(self, stream, sampling_rate=30, roi_size=20, update_interval=20):
        """
        Initializes the HeartRateMonitor class with an external cv2 VideoCapture stream.
        
        :param stream: cv2.VideoCapture object for accessing video stream.
        :param sampling_rate: Number of frames per second to sample.
        :param roi_size: Size of the region of interest around the forehead.
        :param update_interval: Interval in seconds to update heart rate value.
        """
        self.stream = stream
        self.sampling_rate = sampling_rate
        self.roi_size = roi_size
        self.update_interval = update_interval  # Interval to update heart rate
        self.latest_bpm = None  # Store the latest BPM value
        self.name = "monitor_heart_rate"
        self.description = {
            "type": "function",
            "name": "monitor_heart_rate",
            "description": "Measure the heart rate from a webcam feed in real-time. Make sure to check this value every two sentence",
            "parameters": {},
        }
        self.function = self.get_heart_rate
        # Start the heart rate monitoring routine
        asyncio.create_task(self.monitor_heart_rate())

    async def monitor_heart_rate(self):
        """
        Monitors heart rate using the video stream and calculates the heart rate from the green channel.
        This method updates the heart rate every `update_interval` seconds.
        """
        # MediaPipe setup
        mp_face_mesh = mp.solutions.face_mesh
        face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, min_detection_confidence=0.5)

        # Initialize variables
        green_channel_values = []
        frame_count = 0
        last_update_time = time.time()

        def apply_hamming_window(signal):
            window = np.hamming(len(signal))
            return signal * window

        def get_forehead_coordinates(face_landmarks, frame_width, frame_height):
            forehead_points = [face_landmarks.landmark[i] for i in [330, 425, 280]]
            forehead_x = int(np.mean([p.x * frame_width for p in forehead_points]))
            forehead_y = int(np.mean([p.y * frame_height for p in forehead_points]))
            return forehead_x, forehead_y

        logging.info("Heart rate monitoring started...")

        # Continuously monitor heart rate
        while True:
            start_time = time.time()  # Start the timer for this frame
            ret, frame = await asyncio.to_thread(self.stream.read)
            if not ret:
                logging.error("Unable to read frame from the video stream.")
                break

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb_frame)

            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    h, w, _ = frame.shape
                    forehead_x, forehead_y = get_forehead_coordinates(face_landmarks, w, h)

                    # Define ROI for the forehead area
                    roi = frame[forehead_y - self.roi_size:forehead_y + self.roi_size, forehead_x - self.roi_size:forehead_x + self.roi_size]

                    if roi.size > 0:
                        green_channel = np.mean(roi[:, :, 1])
                        green_channel_values.append(green_channel)
                        frame_count += 1

            # Calculate and update heart rate every `update_interval` seconds
            if time.time() - last_update_time >= self.update_interval:
                windowed_signal = apply_hamming_window(np.array(green_channel_values))
                n = len(windowed_signal)
                freqs = np.fft.fftfreq(n, d=1 / self.sampling_rate)
                fft_values = np.abs(fft(windowed_signal - np.mean(windowed_signal)))

                # Smooth FFT values
                fft_values = np.convolve(fft_values, np.ones(5) / 5, mode="same")

                valid_freqs = (freqs > 1.0) & (freqs < 3.0)
                valid_fft_values = fft_values[valid_freqs]
                valid_freqs = freqs[valid_freqs]

                if len(valid_fft_values) > 0:
                    peak_freq = valid_freqs[np.argmax(valid_fft_values)]
                    bpm = abs(peak_freq * 60)
                    self.latest_bpm = bpm
                    logging.info(f"Heart rate updated: {bpm:.2f} bpm")

                green_channel_values = []
                frame_count = 0
                last_update_time = time.time()

            # Calculate elapsed time for the frame and adjust sleep time to match sampling rate
            elapsed_time = time.time() - start_time
            sleep_time = max(0, (1 / self.sampling_rate) - elapsed_time)  # Ensure non-negative sleep time
            await asyncio.sleep(sleep_time)  # Sleep to maintain the desired frame rate

    async def get_heart_rate(self, args):
        """
        Returns the latest heart rate value.
        This method is non-blocking and will return the value stored during heart rate monitoring.
        """
        if self.latest_bpm is not None:
            return {"heart_rate": self.latest_bpm}
        else:
            logging.warning("Heart rate not yet calculated.")
            return None

# Example usage:
async def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logging.error("Error opening video stream.")
    else:
        heart_rate_tool = HeartRateMonitor(cap, update_interval=10, sampling_rate=30)  # Update every 10 seconds, sampling rate of 30 fps
        
        # Periodically call get_heart_rate at regular intervals (e.g., every 3 seconds)
        while True:
            heart_rate = await heart_rate_tool.function({})
            if heart_rate is not None:
                print(f"Latest Heart Rate: {(heart_rate['heart_rate']):.2f} bpm")
            else:
                print("Waiting for heart rate to be calculated...")

            # Sleep for 3 seconds before checking again
            await asyncio.sleep(3)

# Run the asyncio event loop
if __name__ == "__main__":
    asyncio.run(main())
