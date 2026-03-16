# Council OS

**Your private, multi-agent LLM council running locally. Projected and tested on M3 Max MacBook Pro 36GB.**

A fast, always-on CrewAI-powered council (Researcher + Network Scout + Coder + Supreme Moderator) that you can reach from anywhere — OpenWebUI, Cursor, phone, or your work laptop.

Built for exactly what you wanted: coding tasks, remote Q&A, local network/file discovery, and real multi-agent collaboration without the cloud.

## Features

- Full multi-agent council using 4 specialized local models
- Network & file discovery via custom tools (list folders, search NAS, grep, etc.)
- Coding specialist (DeepSeek-Coder 6.7B)
- Remote access from anywhere (Tailscale)
- Seamless integration with OpenWebUI and Cursor
- Always-on via Docker (OS-agnostic, survives reboots)
- Zero cloud cost, fully private.

## Models Used

| Role              | Model                  | Purpose                          |
|-------------------|------------------------|----------------------------------|
| Fast Researcher   | qwen2.5:7b             | Quick context & research         |
| Network Scout     | qwen2.5:14b            | File & local network discovery   |
| Expert Coder      | deepseek-coder:6.7b    | Clean, executable code           |
| Supreme Moderator | qwen2.5:32b            | Final synthesis & decision       |

## Quick Start

### 1. Prerequisites
- macOS (Apple Silicon)
- Homebrew
- **Python 3.12.13 or higher** (required — tiktoken dependency in CrewAI needs it)
- Ollama (`brew install ollama`)
- Pulled models:
  ```bash
  ollama pull qwen2.5:7b
  ollama pull qwen2.5:14b
  ollama pull qwen2.5:32b
  ollama pull deepseek-coder:6.7b
2. Setup the Council
Bashgit clone https://github.com/arthurgeron/CouncilOS.git
cd CouncilOS
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
3. Run it (native)
Bashuvicorn api:app --host 0.0.0.0 --port 8000 --reload
Always-On (Recommended: Docker)
The easiest and most reliable way to run Council OS 24/7:
Create docker-compose.yml and Dockerfile (already in the repo), then:
Bashdocker compose up -d --build
This starts the council as a background service that survives reboots.
To stop:
Bashdocker compose down
Integrations
OpenWebUI (recommended chat UI)
Run OpenWebUI with Docker (recommended):
Bashdocker run -d -p 8080:8080 \
  --add-host=host.docker.internal:host-gateway \
  -v open-webui:/app/backend/data \
  --name open-webui \
  --restart always \
  ghcr.io/open-webui/open-webui:main
Then in OpenWebUI:

Go to Admin Panel → Settings → General → Direct Connections → toggle ON
Add new connection:
Base URL: http://host.docker.internal:8000/v1 (or your Tailscale IP)
Auth: None

Select council-os as your model (or set as default)

Every chat now uses the full council.
Cursor (coding)
Add a custom model in Cursor:

Base URL: http://<your-m3-tailscale-ip>:8000/v1
Model name: council-os
API Key: anything (ollama)

Remote Access (phone, etc.)
Install Tailscale on all devices and join the same tailnet.
Then use your M3’s Tailscale IP (e.g. 100.x.x.x:8000).
Custom Tools
The Network Scout agent has built-in tools for:

Listing folders (list Documents)
Safe network pings
Recursive search / grep (easy to extend)

See tools.py to add more.
Project Structure
textCouncilOS/
├── api.py
├── tools.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── LICENSE
└── README.md
License
MIT License — feel free to use, modify, or build on it however you like.

