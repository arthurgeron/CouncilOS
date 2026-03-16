# Council OS

**Your private, multi-agent LLM council running locally on your M3 Max.**

A fast, always-on CrewAI-powered council (Researcher + Network Scout + Coder + Supreme Moderator) that you can reach from anywhere — OpenWebUI, Cursor, phone, or your work laptop.

Built exactly for what you wanted: coding tasks via Cursor, remote Q&A, local network/file discovery, and real multi-agent flows — all 100% private and offline.

## Features

- Full multi-agent council with 4 specialized local models
- Network & file discovery via custom tools (list folders, search NAS, grep, etc.)
- Dedicated coding agent (DeepSeek-Coder 6.7B)
- Remote access from anywhere via Tailscale
- Seamless integration with OpenWebUI and Cursor
- Always-on via Docker (OS-agnostic, survives reboots)
- Zero cloud cost, fully private

## Models Used

| Role              | Model                  | Purpose                          |
|-------------------|------------------------|----------------------------------|
| Fast Researcher   | qwen2.5:7b             | Quick context & research         |
| Network Scout     | qwen2.5:14b            | File & local network discovery   |
| Expert Coder      | deepseek-coder:6.7b    | Clean, executable code           |
| Supreme Moderator | qwen2.5:32b            | Final synthesis & decision       |

## Quick Start

### 1. Prerequisites
- Docker (https://docs.docker.com/get-docker/)
- Homebrew (on macOS)
- **Python 3.12.13 or higher** (required for CrewAI)
- Ollama (`brew install ollama`)
- Pulled models:
  ```bash
  ollama pull qwen2.5:7b
  ollama pull qwen2.5:14b
  ollama pull qwen2.5:32b
  ollama pull deepseek-coder:6.7b

### 2. Setup the Council
```bash
git clone https://github.com/arthurgeron/CouncilOS.git
cd CouncilOS
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Execution

#### 3.1 Docker
```bash
docker compose up -d --build
```

#### 3.2 Native

##### Setup Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
##### Run the Council
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

###### Run WebUI
```bash
docker run -d -p 8080:8080 --add-host=host.docker.internal:host-gateway -v open-webui:/app/backend/data --name open-webui --restart always ghcr.io/open-webui/open-webui:main
```

## Integrations

### OpenWebUI (included in Docker Compose)
> Access at http://localhost:8080

1. Go to Admin Panel → Settings → General → Direct Connections → toggle ON
2. Add new connection:
   - Base URL: http://host.docker.internal:8000/v1 (or your Tailscale IP)
   - Auth: None
   - Select m3-council as your model (or set as default)

### Cursor (coding)

1. Add custom model:

   - Base URL: http://<your-m3-tailscale-ip>:8000/v1
   - Model name: m3-council
   - API Key: anything (ollama)

### Remote Access
1. Install Tailscale on all devices and join the same tailnet.
2. Use your Host's Tailscale IP (e.g. 100.x.x.x:8000).