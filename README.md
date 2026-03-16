# Council OS

**Your private, multi-agent LLM council running locally. Projected and tested on M3 Max Macbook Pro 36GB.**

A fast, always-on CrewAI-powered council (Researcher + Network Scout + Coder + Supreme Moderator) that you can reach from anywhere — OpenWebUI, Cursor, phone, or your work laptop.

Built for exactly what you wanted: coding tasks, remote Q&A, local network/file discovery, and real multi-agent collaboration without the cloud.

## Features

- Full multi-agent council using 4 specialized local models
- Network & file discovery via custom tools (list folders, search NAS, grep, etc.)
- Coding specialist (DeepSeek-Coder 6.7B)
- Remote access from anywhere (Tailscale)
- Seamless integration with OpenWebUI and Cursor
- Always-on via macOS launchd (starts on boot)
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
  ```

### 2. Setup the Council
```bash
git clone https://github.com/arthurgeron/CouncilOS.git
cd CouncilOS
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Run it
```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

## Integrations

### OpenWebUI (recommended chat UI)
1. In OpenWebUI → Admin Panel → Settings → General → **Direct Connections** → toggle ON
2. Add new connection:
   - Base URL: `http://host.docker.internal:8000/v1` (or your Tailscale IP)
   - Auth: None
3. Select **m3-council** as your model (or set as default)

Every chat now uses the full council.

### Cursor (coding)
Add a custom model in Cursor:
- Base URL: `http://<your-m3-tailscale-ip>:8000/v1`
- Model name: `m3-council`
- API Key: anything (`ollama`)

Cursor will now send coding tasks to your full multi-agent council.

### Remote Access (phone, etc.)
Install **Tailscale** on all devices and join the same tailnet.  
Then use your M3’s Tailscale IP (e.g. `100.x.x.x:8000`).

## Always-On (Boot on Startup)
```bash
cp com.m3.council.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.m3.council.plist
```

The council (and the 32B model) will now start automatically on every boot.

## Custom Tools
The Network Scout agent has built-in tools for:
- Listing folders (`list Documents`)
- Safe network pings
- Recursive search / grep (easy to extend)

See `tools.py` to add more.

## Project Structure
```
CouncilOS/
├── api.py
├── tools.py
├── com.m3.council.plist
├── requirements.txt
├── LICENSE
└── README.md
```

## License
[MIT License](LICENSE) — feel free to use, modify, or build on it however you like.

---

**Made with ❤️ on an M3 Max**  
Your private AI council is ready.
```