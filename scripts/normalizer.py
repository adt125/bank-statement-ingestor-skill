"""
normalizer.py — LLM-powered Transaction Normalizer + Categorizer
Supports: Ollama (local), Gemini, Groq, Anthropic (Claude)
Set LLM_BACKEND env var to switch: ollama | gemini | groq | anthropic
"""

import os
import json
import time
import requests
from dataclasses import dataclass
from typing import Optional
from scripts.pii_filter import CleanTransaction


@dataclass
class NormalizedTransaction:
    date:        str
    description: str
    merchant:    str
    category:    str
    subcategory: str
    amount:      float
    txn_type:    str
    bank:        str
    tags:        list[str]
    confidence:  float
    balance:     Optional[float] = None


# ── Categories (move to scripts/constants.py to centralize) ────────────────
# Attempt to import CATEGORIES from scripts.constants so the agent can manage
# the canonical category list separately. If the constants module is missing,
# fall back to the embedded default so the code remains usable.
try:
    from scripts.constants import CATEGORIES  # user will create/edit this file
except Exception:
    CATEGORIES = """
- Food & Dining (subcategories: Restaurants, Food Delivery, Groceries, Cafes)
- Transport (subcategories: Cab, Metro/Bus, Fuel, Auto)
- Shopping (subcategories: Clothing, Electronics, Amazon/Flipkart, General)
- Utilities (subcategories: Electricity, Water, Internet, Mobile Recharge)
- Entertainment (subcategories: OTT/Streaming, Movies, Events, Gaming)
- Health (subcategories: Pharmacy, Hospital, Lab Tests, Gym)
- Finance (subcategories: EMI, Insurance, Investments, Bank Charges)
- Travel (subcategories: Flights, Hotels, Trains)
- Education (subcategories: Courses, Books, Subscriptions)
- Income (subcategories: Salary, Freelance, Cashback, Refund)
- Transfer (subcategories: UPI Transfer, NEFT, Internal Transfer)
- Other
"""

# The normalizer supports an "agent" backend. When LLM_BACKEND=agent, the
# normalizer will export a normalization payload (prompt + transactions) to a
# JSON file for an external agent to process (the agent can call a chosen
# LLM or perform human-in-the-loop categorization). Use the helper
# `apply_classifications` to convert the agent's JSON output into
# NormalizedTransaction objects.

# ── Prompt builder ────────────────────────────────────────────────────────────

def build_prompt(transactions: list[CleanTransaction]) -> str:
    txn_list = "\n".join(
        f"{i+1}. [{t.date}] {t.description} | ₹{t.amount} | {t.txn_type}"
        for i, t in enumerate(transactions)
    )
    return f"""You are a financial data normalizer for an Indian expense tracker.
Given bank transaction descriptions, extract structured data.

Categories:
{CATEGORIES}

Transactions:
{txn_list}

Return ONLY a JSON array — no markdown, no explanation:
[
  {{
    "index": 1,
    "merchant": "clean merchant name",
    "category": "exact category from list",
    "subcategory": "exact subcategory from list",
    "tags": ["tag1", "tag2"],
    "confidence": 0.95
  }}
]

Rules:
- UPI transfers to people → Transfer > UPI Transfer
- Salary credits → Income > Salary
- ATM → Other > ATM
- confidence: 1.0 = certain, 0.5 = guessed
- Return exactly {len(transactions)} objects in the same order"""


# ── LLM backends ──────────────────────────────────────────────────────────────

def call_ollama(prompt: str) -> str:
    """Local Ollama — zero cost, fully private. `ollama pull llama3` first."""
    resp = requests.post("http://localhost:11434/api/generate", json={
        "model": os.getenv("OLLAMA_MODEL", "llama3"),
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }, timeout=120)
    return resp.json()["response"]


def call_gemini(prompt: str) -> str:
    """Google Gemini Flash — free tier (15 req/min). pip install google-generativeai"""
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash")
    resp  = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"}
    )
    return resp.text


def call_groq(prompt: str) -> str:
    """Groq — fast inference, generous free tier. pip install groq"""
    from groq import Groq
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    resp   = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "llama3-8b-8192"),
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def call_anthropic(prompt: str) -> str:
    """Anthropic Claude — most accurate. pip install anthropic"""
    import anthropic
    client = anthropic.Anthropic()
    resp   = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


# ── Backend selector ──────────────────────────────────────────────────────────

BACKENDS = {
    "ollama":    call_ollama,
    "gemini":    call_gemini,
    "groq":      call_groq,
    "anthropic": call_anthropic,
}

def call_llm(prompt: str) -> str:
    backend = os.getenv("LLM_BACKEND", "ollama").lower()
    # Special "agent" backend: export payload and let an external agent handle it.
    if backend == "agent":
        # write payload to a timestamped file for the agent to pick up
        import json, datetime, os
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        out_dir = os.getenv("NORMALIZER_PAYLOAD_DIR", "./tmp")
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"normalizer_payload_{ts}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"prompt": prompt}, fh, ensure_ascii=False, indent=2)
        print(f"[NORM] Exported normalization payload for agent at: {path}")
        # Signal to caller that agent handling is required by raising a specific error
        raise RuntimeError(f"AGENT_HANDLED_NORMALIZATION: payload written to {path}")

    fn = BACKENDS.get(backend)
    if not fn:
        raise ValueError(f"Unknown LLM_BACKEND '{backend}'. Choose: {list(BACKENDS)}")
    return fn(prompt)


# ── Core normalizer ───────────────────────────────────────────────────────────

def normalize_batch(
    transactions: list[CleanTransaction],
    batch_size:   int = 30,
    retries:      int = 2,
) -> list[NormalizedTransaction]:
    """Normalize a batch of CleanTransaction objects.

    Behavior:
    - If LLM_BACKEND is set to 'agent', the function will export a payload
      file and raise RuntimeError("AGENT_HANDLED_NORMALIZATION: ...").
      The external agent should process the payload and then call
      `apply_classifications` with the agent's JSON output to obtain
      NormalizedTransaction objects.
    - Otherwise, it will call the configured LLM backend as before.
    """
    results = []

    for start in range(0, len(transactions), batch_size):
        batch  = transactions[start : start + batch_size]
        prompt = build_prompt(batch)

        for attempt in range(retries):
            try:
                raw  = call_llm(prompt).strip()
                raw  = raw.replace("```json", "").replace("```", "").strip()
                # Some models wrap in {"transactions": [...]} 
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    parsed = next(iter(parsed.values()))

                for item in parsed:
                    idx  = item["index"] - 1
                    orig = batch[idx]
                    results.append(NormalizedTransaction(
                        date        = orig.date,
                        description = orig.description,
                        merchant    = item.get("merchant", "Unknown"),
                        category    = item.get("category", "Other"),
                        subcategory = item.get("subcategory", ""),
                        amount      = orig.amount,
                        txn_type    = orig.txn_type,
                        bank        = orig.bank,
                        tags        = item.get("tags", []),
                        confidence  = item.get("confidence", 0.5),
                        balance     = orig.balance,
                    ))
                break

            except RuntimeError as re:
                # Special agent-handled case: bubble up so caller can stop and
                # let agent / human-in-the-loop handle categorization.
                raise

            except Exception as e:
                print(f"[WARN] Batch {start} attempt {attempt+1} failed: {e}")
                if attempt == retries - 1:
                    for t in batch:
                        results.append(NormalizedTransaction(
                            date=t.date, description=t.description,
                            merchant="Unknown", category="Other", subcategory="",
                            amount=t.amount, txn_type=t.txn_type, bank=t.bank,
                            tags=[], confidence=0.0, balance=t.balance,
                        ))
                else:
                    time.sleep(1)

    print(f"[NORM] {len(results)} transactions normalized via {os.getenv('LLM_BACKEND','ollama')}")
    return results


# ── Helpers for agent-driven normalization ───────────────────────────────────

def export_normalization_payload(transactions: list[CleanTransaction], out_path: str | None = None) -> str:
    """Write a JSON payload containing the prompt and transactions for an
    external agent to process. Returns the path to the payload file."""
    import json, datetime, os
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = os.getenv("NORMALIZER_PAYLOAD_DIR", "./tmp")
    os.makedirs(out_dir, exist_ok=True)
    path = out_path or os.path.join(out_dir, f"normalizer_payload_{ts}.json")

    prompt = build_prompt(transactions)
    txn_flat = [t.__dict__ for t in transactions]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"prompt": prompt, "transactions": txn_flat}, fh, ensure_ascii=False, indent=2)

    print(f"[NORM] normalization payload exported to: {path}")
    return path


def apply_classifications(classifications: list[dict], transactions: list[CleanTransaction]) -> list[NormalizedTransaction]:
    """Apply a list of classification dicts (from an agent / LLM) to the
    original transactions and return NormalizedTransaction objects.

    The expected `classifications` format is a list of objects like:
    { "index": 1, "merchant": "...", "category": "...", "subcategory": "...", "tags": [...], "confidence": 0.95 }
    """
    results: list[NormalizedTransaction] = []
    for item in classifications:
        idx = item.get("index", 0) - 1
        if idx < 0 or idx >= len(transactions):
            continue
        orig = transactions[idx]
        results.append(NormalizedTransaction(
            date        = orig.date,
            description = orig.description,
            merchant    = item.get("merchant", "Unknown"),
            category    = item.get("category", "Other"),
            subcategory = item.get("subcategory", ""),
            amount      = orig.amount,
            txn_type    = orig.txn_type,
            bank        = orig.bank,
            tags        = item.get("tags", []),
            confidence  = item.get("confidence", 0.0),
            balance     = orig.balance,
        ))
    return results
