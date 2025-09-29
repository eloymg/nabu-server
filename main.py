import asyncio
import io
import logging
import os
import pathlib
import threading
import time
import wave
from http.server import HTTPServer, SimpleHTTPRequestHandler

from aioesphomeapi import (
    APIClient,
    VoiceAssistantAudioSettings,
    VoiceAssistantEventType,
)
from dotenv import load_dotenv
from nabu_agent import execute_main_workflow
from piper import PiperVoice, download_voices
from pymicro_vad import MicroVad
from zeroconf import (
    AddressResolver,
    IPVersion,
    ServiceBrowser,
    ServiceListener,
    Zeroconf,
)

load_dotenv()

PIPER_VOICE = os.environ["PIPER_VOICE"]
NABU_SERVER_URL = os.environ["NABU_SERVER_URL"]

logging.basicConfig(level=logging.INFO)


FILE_PATH = "output.wav"
PORT = 8080

# Make sure the file exists
if not os.path.exists(FILE_PATH):
    with open(FILE_PATH, "wb") as f:
        f.write(b"")  # empty placeholder file


class SingleFileHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/" or self.path == f"/{os.path.basename(FILE_PATH)}":
            self.path = FILE_PATH
        return super().do_GET()


def start_server():
    server = HTTPServer(("0.0.0.0", PORT), SingleFileHandler)
    logging.info(f"Serving {FILE_PATH} on port {PORT}")
    server.serve_forever()


class MyListener(ServiceListener):
    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        print(f"Service {name} added, service info: {info}")


def pcm_to_wav_bytes(
    audio_bytes: bytes,
    n_channels: int = 1,
    sample_width: int = 2,
    frame_rate: int = 16000,
) -> bytes:
    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(frame_rate)
        wf.writeframes(audio_bytes)

    return buffer.getvalue()


class nabuServer:
    def __init__(self):
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.vad = MicroVad()
        self.run_task = None

    async def start(self, address: str, port: int):
        self.api_client = APIClient(address=address, port=port, password="")
        await self.api_client.connect(login=True)
        logging.info("nabu waiting wake work")
        self.api_client.subscribe_voice_assistant(
            handle_start=self.handle_pipeline_start,
            handle_stop=self.stop,
            handle_audio=self.audio,
        )
        try:
            while True:
                await asyncio.sleep(10)
        except KeyboardInterrupt:
            logging.info("Disconnecting...")
            await self.api_client.disconnect()

    async def handle_pipeline_start(
        self, a: str, b: int, c: VoiceAssistantAudioSettings, d: str | None
    ) -> int:
        self.api_client.send_voice_assistant_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START, {}
        )
        self.api_client.send_voice_assistant_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_START, {}
        )
        return 0

    async def run(self):
        self.audio_queue.put_nowait(b"")
        total = b""
        while True:
            chunk = await self.audio_queue.get()
            if not chunk:
                break
            total += chunk
        wav = pcm_to_wav_bytes(total)
        result = await execute_main_workflow(wav)
        tts_duration = self.piper(result)
        self.api_client.send_voice_assistant_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_TTS_STREAM_START, {}
        )
        logging.info(f"sending tts file: {NABU_SERVER_URL}/output.wav")
        self.api_client.media_player_command(
            2232357057,
            media_url=f"{NABU_SERVER_URL}/output.wav",
            device_id=0,
            announcement=True,
        )
        time.sleep(tts_duration)
        self.api_client.send_voice_assistant_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_TTS_STREAM_END, {}
        )
        self.api_client.send_voice_assistant_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END, {}
        )
        self.reset_vad()

    def reset_vad(self):
        self.vad = MicroVad()

    async def stop(self, _: bool):
        self.cancel_run()
        self.reset_vad()
        logging.info("cancelled run task")
        self.api_client.send_voice_assistant_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END, {}
        )

    async def audio(self, data: bytes):
        threshold = 0.5
        speech_prob: float = self.vad.Process10ms(data)
        if speech_prob < 0:
            logging.info("Need more audio")
        elif speech_prob > threshold:
            logging.info("Speech")
        else:
            logging.info("Silence")
            self.api_client.send_voice_assistant_event(
                VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END, {}
            )
            self.run_task = asyncio.create_task(self.run())
        await self.audio_queue.put(data)

    def cancel_run(self):
        if self.run_task and not self.run_task.done():
            self.run_task.cancel()
            self.run_task = None

    def piper(self, input: str) -> float:
        voice = PiperVoice.load(
            pathlib.Path(f"voices/{PIPER_VOICE}/{PIPER_VOICE}.onnx")
        )
        output_file = "output.wav"

        with wave.open(output_file, "wb") as wav_file:
            voice.synthesize_wav(input, wav_file)

        # Reopen to read metadata
        with wave.open(output_file, "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            duration = frames / float(rate)

        return duration


HNAME = "home-assistant-voice-0918ba._esphomelib._tcp.local."


if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    os.makedirs(pathlib.Path(f"voices/{PIPER_VOICE}/"), exist_ok=True)
    download_voices.download_voice(PIPER_VOICE, pathlib.Path(f"voices/{PIPER_VOICE}/"))
    ha_voice_address = os.getenv("HA_VOICE_IP")
    port = os.getenv("HA_VOICE_PORT")
    if ha_voice_address is None or port is None:
        zeroconf = Zeroconf()
        listener = MyListener()
        browser = ServiceBrowser(zeroconf, HNAME, listener)
        resolver = AddressResolver(HNAME)
        finded = False
        while not finded:
            finded = resolver.request(zeroconf, 3000)
            logging.info("Waiting HA voice")
        logging.info("HA connected")
        addresses = resolver.addresses_by_version(IPVersion.V4Only)
        port = resolver.port
        if port is None:
            port = "0"
        address = addresses[0]
        address_str = ""
        for i in address:
            address_str += str(int(i))
            address_str += "."
        ha_voice_address = address_str[:-1]
    nabu_server: nabuServer = nabuServer()
    asyncio.run(nabu_server.start(ha_voice_address, int(port)))
