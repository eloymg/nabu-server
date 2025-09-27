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
    VoiceAssistantEventType,
)
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


async def main(address: str, port: int):
    api = APIClient(address=address, port=port, password="")
    await api.connect(login=True)
    info = await api.device_info_and_list_entities()
    logging.info(info[1])

    async def handle_pipeline_start(a, b, c, d) -> int | None:
        api.send_voice_assistant_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_START, {}
        )
        return 0

    audio_queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def run():
        try:
            while True:
                audio_queue.put_nowait(b"")
                total = b""
                while True:
                    chunk = await audio_queue.get()
                    if not chunk:
                        break
                    total += chunk
                wav = pcm_to_wav_bytes(total)
                result = await execute_main_workflow(wav)
                tts_duration = piper(result)
                api.send_voice_assistant_event(
                    VoiceAssistantEventType.VOICE_ASSISTANT_TTS_STREAM_START, {}
                )
                logging.info(f"sending tts file: {NABU_SERVER_URL}/output.wav")

                api.media_player_command(
                    2232357057,
                    media_url=f"{NABU_SERVER_URL}/output.wav",
                    device_id=0,
                    volume=100,
                )

                time.sleep(tts_duration)
                api.send_voice_assistant_event(
                    VoiceAssistantEventType.VOICE_ASSISTANT_TTS_STREAM_END, {}
                )
                api.send_voice_assistant_event(
                    VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END, {}
                )
        except asyncio.CancelledError:
            logging.info("run cancelled")
            raise  # re-raise so asyncio knows it was cancelled

    async def stop(s):
        global run_task
        cancel_run()
        logging.info("cancelled run task")
        api.send_voice_assistant_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END, {}
        )

    vad = MicroVad()
    threshold = 0.5

    async def audio(data: bytes):
        global run_task
        speech_prob: float = vad.Process10ms(data)
        if speech_prob < 0:
            logging.info("Need more audio")
        elif speech_prob > threshold:
            logging.info("Speech")
        else:
            logging.info("Silence")
            api.send_voice_assistant_event(
                VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END, {}
            )
            run_task = asyncio.create_task(run())

        await audio_queue.put(data)

    def cancel_run():
        global run_task
        if run_task and not run_task.done():
            run_task.cancel()
            run_task = None

    api.subscribe_voice_assistant(
        handle_start=handle_pipeline_start,
        handle_stop=stop,
        handle_audio=audio,
    )
    try:
        while True:
            await asyncio.sleep(10)
    except KeyboardInterrupt:
        logging.info("Disconnecting...")
        await api.disconnect()


HNAME = "home-assistant-voice-0918ba._esphomelib._tcp.local."


def piper(input: str) -> float:
    voice = PiperVoice.load(pathlib.Path(f"voices/{PIPER_VOICE}/{PIPER_VOICE}.onnx"))
    output_file = "output.wav"

    with wave.open(output_file, "wb") as wav_file:
        voice.synthesize_wav(input, wav_file)

    # Reopen to read metadata
    with wave.open(output_file, "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        duration = frames / float(rate)

    return duration


if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    os.makedirs(pathlib.Path(f"voices/{PIPER_VOICE}/"), exist_ok=True)
    download_voices.download_voice(PIPER_VOICE, pathlib.Path(f"voices/{PIPER_VOICE}/"))
    if os.getenv("HA_VOICE_IP") is None:
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
        address = addresses[0]
        address_str = ""
        for i in address:
            address_str += str(int(i))
            address_str += "."
        ha_voice_address = address_str[:-1]
    else:
        ha_voice_address = os.getenv("HA_VOICE_IP")
        port = os.getenv("HA_VOICE_PORT")

    asyncio.run(main(ha_voice_address, int(port)))
