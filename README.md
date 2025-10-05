# Nabu Server

A voice assistant server for Home Assistant that integrates with ESPHome devices to provide voice interaction capabilities using advanced speech processing.

## Features

- **Voice Activity Detection (VAD)**: Real-time voice activity detection using MicroVad
- **Speech-to-Text**: Processes audio from ESPHome voice assistant devices
- **Text-to-Speech**: Generates natural-sounding speech using Piper TTS
- **Home Assistant Integration**: Seamless integration with Home Assistant voice devices via ESPHome API
- **Automatic Device Discovery**: Uses mDNS/Zeroconf for automatic discovery of Home Assistant voice devices
- **HTTP Audio Server**: Serves generated audio files for playback on voice assistant devices
- **Nabu Agent Workflow**: Integrates with nabu-agent for intelligent voice command processing

## Requirements

- Python 3.13 or higher
- Docker (optional, for containerized deployment)
- NVIDIA GPU with CUDA support (optional, for accelerated inference)
- Home Assistant with ESPHome voice assistant device

## Installation

### Using Docker (Recommended)

1. Clone the repository:
```bash
git clone https://github.com/eloymg/nabu-server.git
cd nabu-server
```

2. Create a `.env` file with required environment variables:
```bash
PIPER_VOICE=en_US-lessac-medium
NABU_SERVER_URL=http://your-server-ip:8080
```

3. Build and run using the provided script:
```bash
chmod +x run.sh
./run.sh
```

Or manually with Docker:
```bash
docker build . -t nabu-server:latest
docker run -v .env:/.env -v $HOME/.cache/:/root/.cache -p 8080:8080 --network host nabu-server:latest
```

### Manual Installation

1. Install uv package manager:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Clone the repository:
```bash
git clone https://github.com/eloymg/nabu-server.git
cd nabu-server
```

3. Install dependencies:
```bash
uv sync
```

4. Create a `.env` file with environment variables (see Configuration section)

5. Run the server:
```bash
uv run python main.py
```

## Configuration

The server requires the following environment variables to be set in a `.env` file:

| Variable | Description | Example |
|----------|-------------|---------|
| `PIPER_VOICE` | Piper TTS voice model to use | `en_US-lessac-medium` |
| `NABU_SERVER_URL` | Public URL where the server is accessible | `http://192.168.1.100:8080` |
| `HA_VOICE_IP` | (Optional) Home Assistant voice device IP address | `192.168.1.50` |
| `HA_VOICE_PORT` | (Optional) Home Assistant voice device port | `6053` |

**Note**: If `HA_VOICE_IP` and `HA_VOICE_PORT` are not provided, the server will automatically discover the Home Assistant voice device using mDNS/Zeroconf.

## Usage

1. Start the nabu-server (using Docker or manual installation)
2. The server will:
   - Download the specified Piper voice model (if not cached)
   - Start an HTTP server on port 8080 to serve audio files
   - Discover or connect to your Home Assistant voice device
   - Wait for voice commands from the ESPHome device

3. The voice assistant pipeline works as follows:
   - User activates the wake word on the ESPHome device
   - Audio is streamed to the nabu-server
   - Voice Activity Detection identifies when speech ends
   - Audio is processed through the nabu-agent workflow
   - Response is synthesized using Piper TTS
   - Audio is sent back to the ESPHome device for playback

## Architecture

```
ESPHome Device → nabu-server → nabu-agent → Response
                      ↓
                  Piper TTS → Audio File
                      ↓
                 HTTP Server → ESPHome Device
```

### Components

- **nabuServer**: Main server class that handles the voice assistant pipeline
- **HTTP Server**: Serves generated audio files on port 8080
- **Voice Activity Detection**: MicroVad for real-time speech detection
- **Text-to-Speech**: Piper TTS for natural voice synthesis
- **ESPHome Integration**: aioesphomeapi for communication with Home Assistant devices

## Development

### Running Logs

To debug ESPHome device logs:
```bash
uv run python logs.py
```

### Project Structure

- `main.py` - Main server implementation
- `logs.py` - ESPHome device log viewer
- `Dockerfile` - Container image definition
- `pyproject.toml` - Python project configuration
- `run.sh` - Docker build and run script

## Dependencies

Core dependencies:
- `aioesphomeapi` - ESPHome API client
- `nabu-agent` - Voice command processing workflow
- `piper-tts` - Text-to-speech synthesis
- `pymicro-vad` - Voice activity detection
- `zeroconf` - mDNS service discovery

## Docker Image

The Docker image is based on NVIDIA CUDA runtime for GPU acceleration and includes:
- CUDA 12.3.2 with cuDNN 9
- Python 3.13
- FFmpeg for audio processing
- spotify-connect binary

Published images are available at:
```
ghcr.io/eloymg/nabu-server:latest
```

## License

This project is part of the nabu voice assistant ecosystem. See the repository for license information.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Acknowledgments

- [Piper TTS](https://github.com/rhasspy/piper) - High quality text-to-speech
- [ESPHome](https://esphome.io/) - Device integration framework
- [nabu-agent](https://github.com/und1n3/nabu-agent) - Voice workflow processing
