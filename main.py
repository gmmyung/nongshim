import asyncio
import json
import base64
import os
from collections import deque
import logging
from dotenv import load_dotenv
import pyaudio
import websockets
from audio import AudioPlayer, AudioRecorder


class RealTimeChat:
    URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
    BYTES_PER_FRAME = 2  # PCM16 is 2 bytes per frame
    SAMPLE_RATE = 24000

    def __init__(
        self,
        input_device_index=None,
        output_device_index=None,
        voice="alloy",
        turn_threshold=0.5,
        prefix_padding_ms=300,
        silence_duration_ms=500,
        tempreature=0.8,
        input_buffer_size=4096,
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

    @classmethod
    async def setup(cls):
        self = cls()
        self.websocket = await websockets.connect(self.URL, extra_headers=self.headers)
        logging.info("Connected to OpenAI Realtime API")
        return self

    async def update(
        self,
        instructions,
        voice,
        turn_threshold,
        prefix_padding_ms,
        silence_duration_ms,
        tempreature,
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
                        "voice": voice,
                        "turn_detection": {
                            "type": "server_vad",
                            "threshold": turn_threshold,
                            "prefix_padding_ms": prefix_padding_ms,
                            "silence_duration_ms": silence_duration_ms,
                        },
                        "temperature": tempreature,
                        "input_audio_transcription": {
                            "model": "whisper-1",
                        },
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

    def audio_input_callback(self, in_data, frame_count, time_info, status):
        self.input_buffer.extend(in_data)
        if len(self.input_buffer) == self.input_buffer_size:
            logging.info("Input buffer is overflowing")
        return (bytes(), pyaudio.paContinue)

    def audio_output_callback(self, in_data, frame_count, time_info, status):
        total_bytes = self.BYTES_PER_FRAME * frame_count
        for response in self.responses.values():
            if len(response.audio) > 0:
                if len(response.audio) >= self.BYTES_PER_FRAME:
                    end_idx = min(len(response.audio), total_bytes)
                    frame = response.audio[:end_idx]
                    response.audio = response.audio[end_idx:]
                    frame = bytes(total_bytes - end_idx) + frame
                    return (frame, pyaudio.paContinue)
        return (bytes(frame_count * self.BYTES_PER_FRAME), pyaudio.paContinue)

    async def message_handler(self, message):
        data = json.loads(message)
        message_type = data.get("type")
        if message_type in self.pending_events.keys():
            future = self.pending_events[message_type].get_nowait()
            future.set_result(data)
            del self.pending_events[message_type]
        elif message_type == "created":
            logging.info(json.dumps(data, indent=4))
        elif message_type.startswith("input_audio_buffer"):
            self.input_audio_buffer_message_handler(message_type, data)
        elif message_type.startswith("response"):
            self.response_message_handler(message_type, data)
        elif message_type == "error":
            logging.error(json.dumps(data, indent=4))
        else:
            logging.debug(json.dumps(data, indent=4))

    def input_audio_buffer_message_handler(self, message_type, data):
        message = message_type.split(".")[1]
        if message == "speech_started":
            logging.info("User started speaking")
        elif message == "speech_stopped":
            logging.info("User stopped speaking")
        elif message == "committed":
            logging.info("User input audio buffer was committed")

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
        # update = self.update(
        #     instructions="",
        #     voice=self.voice,
        #     turn_threshold=self.turn_threshold,
        #     prefix_padding_ms=self.prefix_padding_ms,
        #     silence_duration_ms=self.silence_duration_ms,
        #     tempreature=0.8,
        # )

        # await asyncio.gather(message_polling_task, buffer_polling_task, update)
        await asyncio.gather(message_polling_task, buffer_polling_task)

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

            await asyncio.sleep(0.01)

    async def message_polling_loop(self):
        while True:
            try:
                async for message in self.websocket:
                    await self.message_handler(message)

            except websockets.exceptions.ConnectionClosedError:
                logging.warning("Connection closed")
                break

            await asyncio.sleep(0.01)


class Response:
    def __init__(self, status):
        self.transcript = ""
        self.audio = bytes()
        self.status = status


async def main():
    load_dotenv()
    chat = await RealTimeChat.setup()
    await chat.run()


if __name__ == "__main__":
    from rich.logging import RichHandler

    FORMAT = "%(message)s"
    logging.basicConfig(
        level="INFO", format=FORMAT, datefmt="[%X]", handlers=[RichHandler()]
    )
    asyncio.run(main())
