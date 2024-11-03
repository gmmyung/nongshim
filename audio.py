import asyncio
import pyaudio

FORMAT = pyaudio.paInt16
CHANNELS = 1


class AudioRecorder:
    def __init__(
        self,
        input_device_index=None,
        sample_rate=16000,
        frames_per_buffer=512,
        callback=None,
    ):
        self.sample_rate = sample_rate
        self.frames_per_buffer = frames_per_buffer
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            input_device_index=input_device_index,
            format=FORMAT,
            channels=CHANNELS,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.frames_per_buffer,
            stream_callback=callback,
        )


class AudioPlayer:
    def __init__(
        self,
        output_device_index=None,
        sample_rate=16000,
        frames_per_buffer=512,
        callback=None,
    ):
        self.sample_rate = sample_rate
        self.frames_per_buffer = frames_per_buffer
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            output_device_index=output_device_index,
            format=FORMAT,
            channels=CHANNELS,
            rate=self.sample_rate,
            output=True,
            frames_per_buffer=self.frames_per_buffer,
            stream_callback=callback,
        )


async def main():
    def callback(in_data, frame_count, time_info, status):
        return (in_data, pyaudio.paContinue)

    AudioRecorder(callback=callback)

    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
