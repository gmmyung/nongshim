import os
import cv2
import dotenv
import logging
from openai import AsyncOpenAI
import base64

# Define the Tool class
class Tool:
    def __init__(self, name, description, function):
        self.name = name
        self.description = description
        self.function = function

# Define the Webcam Capture and Description Tool
class ImageDescriptionTool(Tool):
    def __init__(self, openai_api_key, stream):
        self.name = "image_description"
        self.description = {
            "type": "function",
            "name": "image_description",
            "description": "Capture an image of the working environment using the robot's webcam and generate a description of the image. You do not need to get permission to take photos of the surroundings.",
            "parameters": {}
        }
        self.openai_api_key = openai_api_key
        self.function = self.capture_and_describe_image
        self.client = AsyncOpenAI()
        self.cap = stream

    async def capture_and_describe_image(self, arguments):
        image = self.capture_image()
        logging.info("Captured image")
        image_base64 = self.convert_image_to_base64(image)
        logging.info("Converted image to base64")
        description = await self.get_image_description(image_base64)
        logging.info("Got image description")

        return {"description": description}

    def capture_image(self):
        # Open the webcam (default camera 0)

        # Check if the webcam is opened correctly
        if not self.cap.isOpened():
            raise Exception("Could not open webcam")

        # Capture a single frame
        ret, frame = self.cap.read()

        if not ret:
            raise Exception("Failed to capture image")

        # Release the webcam after capture

        # Return the captured image
        return frame

    def convert_image_to_base64(self, image):
        # Convert the image (numpy array) to a format suitable for OpenAI API (base64 encoded)
        _, buffer = cv2.imencode('.jpg', image)
        img_bytes = buffer.tobytes()
        image_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return image_base64

    async def get_image_description(self, image_base64):
        # Query OpenAI API for image description
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "You are a farmer assisting robot that can capture images from the robot's camera. Descibe the following image:"},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_base64}",
                                    }
                                },
                            ],
                        }
                    ],
            )

            description = response.choices[0].message.content
            return description
        except Exception as e:
            return f"Error while getting description: {e}"

    def close(self):
        self.cap.release()

# Usage Example:
if __name__ == "__main__":
    dotenv.load_dotenv()
    openai.api_key = os.getenv("OPENAI_API_KEY")

    # Create the Image Description Tool
    tool = ImageDescriptionTool(openai_api_key=openai.api_key)

    # You can now call the tool's function asynchronously
    import asyncio
    result = asyncio.run(tool.capture_and_describe_image({}))
    print(result)
