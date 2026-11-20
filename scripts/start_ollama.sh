#!/usr/bin/env bash
# Helper script to launch and configure local Ollama for 100% free offline JARVIS
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR"

echo "=========================================="
echo "🦙 Initializing Local Free Ollama Engine"
echo "=========================================="

if ! command -v ollama &>/dev/null; then
    echo "❌ Ollama is not found in PATH! Install via: brew install ollama"
    exit 1
fi

# Check if Ollama server is already running
if ! curl -s http://127.0.0.1:11434/api/tags &>/dev/null; then
    echo "Starting Ollama server daemon in background..."
    nohup ollama serve > /tmp/ollama.log 2>&1 &
    sleep 2
fi

if curl -s http://127.0.0.1:11434/api/tags &>/dev/null; then
    echo "✅ Ollama server is running at http://127.0.0.1:11434"
else
    echo "⚠️ Ollama daemon start attempted. Check /tmp/ollama.log if needed."
fi

# Check available models
MODELS=$(curl -s http://127.0.0.1:11434/api/tags | grep -o '"name":"[^"]*' | cut -d'"' -f4 || true)
if [ -z "$MODELS" ]; then
    echo "No local Ollama model found yet. Recommended to run:"
    echo "  ollama pull llama3.2"
    echo "  ollama pull mistral"
else
    echo "Available local models:"
    echo "$MODELS"
fi

echo "Configuring JARVIS to use Local Ollama Engine..."
"$DIR/.venv/bin/python" -c "
from memory import config_manager
config_manager.save_provider_mode('pipeline')
config_manager.save_pipeline(stt='stt_whisper', llm='llm_openai', tts='tts_system')
config_manager.save_provider_config('llm_openai', {
    'base_url': 'http://127.0.0.1:11434/v1',
    'model': 'llama3.2',
    'api_key': 'ollama',
})
print('✅ Local Ollama provider pipeline configured in config/api_keys.json!')
"

echo "🎉 Local offline engine is active! Start JARVIS with: ./run.sh"
