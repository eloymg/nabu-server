import asyncio
import io
import logging
import os
import pathlib
import time
import wave

from aioesphomeapi import (
    APIClient,
    VoiceAssistantAudioSettings,
    VoiceAssistantEventType,
)
from nabu_agent import execute_main_workflow
from piper import PiperVoice, download_voices
from zeroconf import (
    AddressResolver,
    IPVersion,
    ServiceBrowser,
    ServiceListener,
    Zeroconf,
)

PIPER_VOICE = os.environ["PIPER_VOICE"]

logging.basicConfig(level=logging.INFO)


class MyListener(ServiceListener):
    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        print(f"Service {name} updated")

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        print(f"Service {name} removed")

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        print(f"Service {name} added, service info: {info}")


def pcm_to_wav_bytes(
    audio_bytes: bytes, n_channels=1, sample_width=2, frame_rate=44100
) -> bytes:
    buffer = io.BytesIO()

    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(n_channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(frame_rate)
        wf.writeframes(audio_bytes)

    return buffer.getvalue()


async def main(address, port):
    api = APIClient(address=address, port=port, password="")
    await api.connect(login=True)
    device_info = await api.device_info_and_list_entities()
    print(device_info)

    async def handle_pipeline_start(
        conversation_id: str,
        flags: int,
        audio_settings: VoiceAssistantAudioSettings,
        wake_word_phrase: str | None,
    ) -> int | None:
        print("aconversation_id:", conversation_id)
        print("flags:", flags)
        print("audio_settings:", audio_settings)
        print("wake_word_phrase:", wake_word_phrase)
        api.send_voice_assistant_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_START, {}
        )
        return 0

    audio_queue = asyncio.Queue()

    async def run():
        try:
            while True:
                audio_queue.put_nowait(None)
                total = b""
                while True:
                    chunk = await audio_queue.get()
                    if not chunk:
                        break
                    total += chunk
                wav = pcm_to_wav_bytes(total, 1, 2, 16000)
                result = await execute_main_workflow(wav)
                tts_duration = piper(result)
                api.send_voice_assistant_event(
                    VoiceAssistantEventType.VOICE_ASSISTANT_TTS_STREAM_START, {}
                )
                api.media_player_command(
                    2232357057,
                    # media_url="https://testfiledownload.net/wp-content/uploads/2024/10/1.8-MB.flac",
                    media_url="http://192.168.0.11:8000/output.wav",
                    device_id=0,
                )
                time.sleep(tts_duration)
                api.send_voice_assistant_event(
                    VoiceAssistantEventType.VOICE_ASSISTANT_TTS_STREAM_END, {}
                )
                api.send_voice_assistant_event(
                    VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END, {}
                )
        except asyncio.CancelledError:
            print("run cancelled")
            raise  # re-raise so asyncio knows it was cancelled

    async def stop(s):
        global play_task
        cancel_play()
        print("Cancelled:", s)
        api.send_voice_assistant_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END, {}
        )

    async def audio(data):
        global play_task

        print(audio_queue.qsize())
        if audio_queue.qsize() == 100:
            api.send_voice_assistant_event(
                VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END, {}
            )
            # start play in a task so we can cancel it later
            play_task = asyncio.create_task(run())

        await audio_queue.put(data)

    def cancel_play():
        global play_task
        if play_task and not play_task.done():
            play_task.cancel()
            play_task = None

    async def finish(f):
        print("finish:", f)

    api.subscribe_voice_assistant(
        handle_start=handle_pipeline_start,
        handle_stop=stop,
        handle_audio=audio,
        handle_announcement_finished=finish,
    )
    try:
        while True:
            await asyncio.sleep(10)
    except KeyboardInterrupt:
        print("Disconnecting...")
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
    os.makedirs(pathlib.Path(f"voices/{PIPER_VOICE}/"), exist_ok=True)
    download_voices.download_voice(PIPER_VOICE, pathlib.Path(f"voices/{PIPER_VOICE}/"))
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
    asyncio.run(main(address_str[:-1], port))
