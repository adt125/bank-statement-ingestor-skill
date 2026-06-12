# LLM Backends Reference

The normalizer's `call_llm()` in `scripts/normalizer.py` dispatches to one of these backends based on the `LLM_BACKEND` env var.

## Comparison

| Backend | Cost | Speed | Privacy | JSON reliability | Setup |
|---|---|---|---|---|---|
| **Ollama** (local) | Free | Medium | 100% private | Good (with `format: json`) | Install + pull model |
| **Gemini Flash** | Free tier / very cheap | Fast | Google servers | Excellent (native JSON mode) | API key |
| **Groq** | Free tier / very cheap | Fastest | Groq servers | Good (`json_object` mode) | API key |
| **Anthropic** | Paid ($0.003/1K tokens) | Fast | Anthropic servers | Excellent | API key |

**Recommendation for expense trackers**: Gemini Flash or Groq — both have a free tier that easily handles personal use, and both support JSON mode natively.

---

## Ollama (local, free)

```bash
# Install
brew install ollama           # macOS
# or: https://ollama.ai/download for Windows/Linux

# Pull a model (pick one)
ollama pull llama3            # best accuracy ~4GB
ollama pull mistral           # good balance ~4GB
ollama pull phi3              # lightest ~2GB

# Start the server (runs automatically on macOS)
ollama serve
```

```python
# Already in normalizer.py — no changes needed
export LLM_BACKEND=ollama
export OLLAMA_MODEL=llama3    # optional, defaults to llama3
```

**Note**: Ollama sometimes wraps JSON in a dict like `{"transactions": [...]}`. The normalizer handles this automatically.

---

## Gemini Flash (Google, free tier)

Free tier: 15 req/min, 1M tokens/day — more than enough for personal use.

```bash
pip install google-generativeai
```

Get API key: https://aistudio.google.com/app/apikey (free, no billing needed)

```bash
export LLM_BACKEND=gemini
export GEMINI_API_KEY=your-key-here
```

---

## Groq (fastest inference, free tier)

Free tier: generous daily limits, effectively free for personal use.

```bash
pip install groq
```

Get API key: https://console.groq.com (free account)

```bash
export LLM_BACKEND=groq
export GROQ_API_KEY=your-key-here
export GROQ_MODEL=llama3-8b-8192   # optional, or: mixtral-8x7b-32768
```

---

## Anthropic Claude (most accurate)

Best accuracy for ambiguous transactions, but costs money.

```bash
pip install anthropic
```

```bash
export LLM_BACKEND=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

Approximate cost: a month of personal bank statements (~500 transactions) costs < $0.05.

---

## Switching backends at runtime

```python
import os
os.environ["LLM_BACKEND"] = "gemini"

from scripts.normalizer import normalize_batch
results = normalize_batch(transactions)
```

---

## Adding a new backend

Add a function to `normalizer.py` and register it in `BACKENDS`:

```python
def call_openai(prompt: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content

BACKENDS["openai"] = call_openai
```
