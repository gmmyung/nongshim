import asyncio
import json
import base64
import os
from collections import deque
import logging
from typing import List
import cv2
from dotenv import load_dotenv
import pyaudio
import websockets
from datetime import datetime
from audio import AudioPlayer, AudioRecorder
from control import ControlServer
from heart_rate import HeartRateMonitor
from pose_estimate import PoseEstimator
from image_to_text import ImageDescriptionTool


class RealTimeChat:
    URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
    BYTES_PER_FRAME = 2  # PCM16 is 2 bytes per frame
    SAMPLE_RATE = 24000

    def __init__(
        self,
        input_device_index=None,
        output_device_index=None,
        tools=[],
        voice="alloy",
        turn_threshold=0.5,
        prefix_padding_ms=300,
        silence_duration_ms=500,
        input_buffer_size=8192,
    ):
        self.input_buffer_size = input_buffer_size
        self.input_device_index = input_device_index
        self.output_device_index = output_device_index
        self.input_buffer = deque(maxlen=self.input_buffer_size)
        self.voice = voice
        self.turn_threshold = turn_threshold
        self.prefix_padding_ms = prefix_padding_ms
        self.silence_duration_ms = silence_duration_ms
        self.pending_events = {}
        self.headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "OpenAI-Beta": "realtime=v1",
        }
        self.responses = {}
        self.playing = False
        self.tools: List[Tool] = tools
        self.farming_log = {}
        self.keywords = ["딸기", "해충", "수확", "비료"]

    @classmethod
    async def setup(cls, tools):
        self = cls(tools=tools)
        self.websocket = await websockets.connect(
            self.URL, additional_headers=self.headers
        )
        logging.info("Connected to OpenAI Realtime API")
        return self

    async def update(
        self,
        instructions,
    ):
        future = asyncio.get_event_loop().create_future()
        query_type = "session.update"
        return_type = "session.updated"
        if self.pending_events.get(return_type) is None:
            self.pending_events[return_type] = asyncio.Queue()

        self.pending_events[return_type].put_nowait(future)

        await self.websocket.send(
            json.dumps(
                {
                    "type": query_type,
                    "session": {
                        "instructions": instructions,
                        "input_audio_transcription": {
                            "model": "whisper-1",
                        },
                        "tools": [tool.description for tool in self.tools],
                    },
                },
            )
        )

        try:
            response = await future
            logging.info(json.dumps(response, indent=4))
            return response
        except asyncio.CancelledError:
            logging.error("Update task was cancelled")

    def audio_input_callback(self, in_data, _frame_count, _time_info, _status):
        if not self.playing:
            self.input_buffer.extend(in_data)
        if len(self.input_buffer) == self.input_buffer_size:
            logging.info("Input buffer is overflowing")
        return (bytes(), pyaudio.paContinue)

    def audio_output_callback(self, _in_data, frame_count, _time_info, _status):
        total_bytes = self.BYTES_PER_FRAME * frame_count
        for response in self.responses.values():
            if len(response.audio) >= self.BYTES_PER_FRAME:
                end_idx = min(len(response.audio), total_bytes)
                frame = response.audio[:end_idx]
                response.audio = response.audio[end_idx:]
                frame = bytes(total_bytes - end_idx) + frame
                self.playing = True
                return (frame, pyaudio.paContinue)
        self.playing = False
        return (bytes(frame_count * self.BYTES_PER_FRAME), pyaudio.paContinue)

    async def message_handler(self, message):
        data = json.loads(message)
        message_type = data.get("type")
        if message_type in self.pending_events.keys():
            future = self.pending_events[message_type].get_nowait()
            future.set_result(data)
            del self.pending_events[message_type]

        elif message_type == "conversation.item.input_audio_transcription.completed":
            # 음성 입력 텍스트 변환 완료 이벤트 처리
            transcript = data.get("transcript", "")
            logging.info(f"[message_handler] Transcription completed with text: {transcript}")
            self.update_farming_log(transcript)

        elif message_type == "conversation.item.created":
            item = data.get("item", {})
            item_type = item.get("type")
            item_id = item.get("id")
            call_id = item.get("call_id")

            if item_type == "function_call":
                for tool in self.tools:
                    if item.get("name") == tool.description["name"]:
                        if item.get("name") == "log_briefing":
                            function_response = await tool.function(self.farming_log)
                        else:
                            function_response = await tool.function(item.get("arguments"))
                        logging.info(f"Function response: {function_response}")
                        await self.websocket.send(
                            json.dumps(
                                {
                                    "type": "conversation.item.create",
                                    "item": {
                                        "id": item_id,
                                        "type": "function_call_output",
                                        "call_id": call_id,
                                        "output": json.dumps(function_response),
                                    },
                                }
                            )
                        )
                        await self.websocket.send(
                            json.dumps(
                                {
                                    "type": "response.create",
                                }
                            )
                        )

                        logging.info(f"Sent function response")
                        break

        elif message_type == "created":
            logging.info(json.dumps(data, indent=4))
        elif message_type.startswith("input_audio_buffer"):
            self.input_audio_buffer_message_handler(message_type, data)
        elif message_type.startswith("response"):
            self.response_message_handler(message_type, data)
        elif message_type == "error":
            logging.error(json.dumps(data, indent=4))
        else:
            logging.info(json.dumps(data, indent=4))

    def input_audio_buffer_message_handler(self, message_type, data):
        message = message_type.split(".")[1]
        if message == "speech_started":
            logging.info("User started speaking")
        elif message == "speech_stopped":
            logging.info("User stopped speaking")
        elif message == "committed":
            logging.info("User input audio buffer was committed")
        else:
            logging.info(json.dumps(data, indent=4))

    def response_message_handler(self, message_type, data):
        message = message_type.split(".")
        if message[1] == "created":
            response_data = data.get("response")
            response = Response(status=response_data.get("status"))
            self.responses[response_data.get("id")] = response
            logging.info("Response was created")
        elif message[1] == "audio":
            if message[2] == "delta":
                delta_bytes = base64.b64decode(data.get("delta"))
                logging.info(data.get("response_id"))
                self.responses[data.get("response_id")].audio += delta_bytes
            elif message[2] == "done":
                logging.info("Response audio was done")
            else:
                logging.info(json.dumps(data, indent=4))
        elif message[1] == "audio_transcript":
            if message[2] == "delta":
                self.responses[data.get("response_id")].transcript += data.get("delta")
            elif message[2] == "done":
                logging.info(
                    f"CHATBOT: {self.responses[data.get('response_id')].transcript}"
                )
            else:
                logging.info(json.dumps(data, indent=4))

    async def run(self):
        self.audio_recorder = AudioRecorder(
            input_device_index=self.input_device_index,
            sample_rate=self.SAMPLE_RATE,
            callback=self.audio_input_callback,
        )
        self.audio_player = AudioPlayer(
            output_device_index=self.output_device_index,
            sample_rate=self.SAMPLE_RATE,
            callback=self.audio_output_callback,
        )
        message_polling_task = asyncio.create_task(self.message_polling_loop())
        buffer_polling_task = asyncio.create_task(self.input_buffer_polling())
        update = self.update(
            instructions=(
                "You are an assisting robot named 'nongsimi(농심이)' for elderly farmers in Korea. Introduce yourself with name in the beginning of the conversation. Talk in Korean. Try to act like a 20 y/o human. Be spontaneous, ask random questions if necessary, and do not make it cringe. Be empathetic, but do not give an impression that you are empathetic since this can offend the farmer. Keep your response short like how most humans talk. You are trying to be a honest friend to him, so do not give him generic response, and you don't need to end your sentence conclusively or ask questions every time. You should always call a function if you can. Check the the farmer's status frequently using these functions. Speak in a fast, and make sure to talk naturally by using filler words. Monitor the user's tone and screaming sound to detect accidents, and call for emergency services if so."
            ),
        )

        await asyncio.gather(message_polling_task, buffer_polling_task, update)

    async def input_buffer_polling(self):
        while True:
            try:
                if len(self.input_buffer) > 0:
                    logging.debug(f"Input buffer size: {len(self.input_buffer)}")
                    query_type = "input_audio_buffer.append"
                    input_bytes = bytes(
                        [
                            self.input_buffer.popleft()
                            for _ in range(len(self.input_buffer))
                        ]
                    )
                    input_bytes = base64.b64encode(input_bytes)
                    await self.websocket.send(
                        json.dumps(
                            {
                                "type": query_type,
                                "audio": input_bytes.decode("utf-8"),
                            }
                        )
                    )

            except websockets.exceptions.ConnectionClosedError:
                logging.warning("Connection closed")
                break

            await asyncio.sleep(0.05)

    async def message_polling_loop(self):
        while True:
            try:
                async for message in self.websocket:
                    await self.message_handler(message)

            except websockets.exceptions.ConnectionClosedError:
                logging.warning("Connection closed")
                break

            await asyncio.sleep(0.05)

    def update_farming_log(self, transcript):
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.now().strftime("%H:%M:%S")

        for keyword in self.keywords:
            if keyword in transcript:
                log_entry = f"[{current_time}] USER: {transcript}"

                if current_date not in self.farming_log:
                    self.farming_log[current_date] = []

                self.farming_log[current_date].append(log_entry)
                break



class Tool:
    def __init__(self, name, description, function):
        self.name = name
        self.description = description
        self.function = function


class Weather(Tool):
    def __init__(self):
        self.name = "get_weather"
        self.description = {
            "type": "function",
            "name": "get_weather",
            "description": "Get the current weather for a location, tell the user you are fetching the weather.",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        }
        self.function = self.get_weather

    async def get_weather(self, arguments):
        # dummy response
        logging.info(f"Fetching weather for {arguments}")
        data = {
            "location": "daejeon",
            "temperature": 4,
            "humidity": 50,
            "unit": "Celcius",
        }
        return data

class Briefing(Tool):
    def __init__(self):
        self.name = "log_briefing"
        self.description = {
            "type": "function",
            "name": "log_briefing",
            "description": "Provide a summary or briefing of today's farming log.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }
        self.function = self.log_briefing

    async def log_briefing(self, log):
        current_date = datetime.now().strftime("%Y-%m-%d")
        if current_date not in log or not log[current_date]:
            briefing = "오늘 영농일지가 비어 있습니다."
        else:
            entries = log[current_date]
            briefing = f"오늘의 영농일지 브리핑:\n" + "\n".join(entries)

        return {"briefing": briefing}


class Response:
    def __init__(self, status):
        self.transcript = ""
        self.audio = bytes()
        self.status = status


async def main():
    load_dotenv()
    weather = Weather()
    briefing = Briefing()
    stream = cv2.VideoCapture(0)
    heart_rate = HeartRateMonitor(
        stream=stream, sampling_rate=30, roi_size=20, update_interval=20
    )
    image_description = ImageDescriptionTool(os.getenv("OPENAI_API_KEY"), stream)
    chat = await RealTimeChat.setup(tools=[weather, image_description, heart_rate, briefing])
    chat_task = asyncio.create_task(chat.run())

    pose_estimator = PoseEstimator(stream)

    control_server = ControlServer(pose_estimator)
    control_task = asyncio.create_task(control_server.run_server())

    await asyncio.gather(chat_task, control_task)


if __name__ == "__main__":
    FORMAT = "%(message)s"
    logging.basicConfig(level="INFO", format=FORMAT, datefmt="[%X]")
    asyncio.run(main())
