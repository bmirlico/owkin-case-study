# Owkin Agent POC

A 4-hour proof of concept for the Owkin Forward Deployed Engineer take-home: a web app where a non-technical user asks natural-language questions about a cancer-genomics CSV, and an LLM agent orchestrates two Python functions to answer.

---

## Demo

[Watch the walkthrough](TODO_VIDEO_URL)

---

## What it does

The app exposes a chat UI in the browser. The user types a question; the backend forwards it to Claude (`claude-sonnet-4-6`) using the **Anthropic native tool-use API**, with two tools registered:

- `get_targets(cancer_name)` — list of genes for a cancer indication.
- `get_expressions(genes, cancer_name)` — `{gene: median_value}` for a list of genes, scoped to a cancer.

The model decides whether to call a tool, which one, and — for the chained queries — whether to call them in sequence. Tool results are fed back into the conversation; the model produces a final natural-language answer.

### Reference queries supported

| # | User query | Behaviour |
|---|------------|-----------|
| 1 | *How can you help me?* | Plain text answer describing capabilities and the available cancer indications. No tool calls. |
| 2 | *What are the main genes involved in lung cancer?* | One tool call: `get_targets("lung")` → answer with the gene list. |
| 3 | *What is the median value expression of genes involved in breast cancer?* | **Chained**: `get_targets("breast")` → `get_expressions([...], "breast")` → answer. |
| 4 | *What is the median value expression of genes involved in esophageal cancer?* | The dataset doesn't include esophageal — the model says so explicitly and lists the 10 indications it does cover, **without inventing data**. |

### Sample output (query 3)

```
🔧 get_targets({"cancer_name":"breast"})
↳ get_targets → ["BRCA2","BRCA1","TP53","GATA3","CDH1","ESR1","MAP3K1","HER2","PIK3CA","AKT1"]
🔧 get_expressions({"genes":[...], "cancer_name":"breast"})
↳ get_expressions → {"BRCA2":0.032,"BRCA1":0.094,...}

| Gene   | Median Expression |
|--------|-------------------|
| BRCA2  | 0.032 |
| BRCA1  | 0.094 |
| TP53   | 0.233 |
| ...    | ...   |
```

Available cancer indications in the bundled CSV: `breast, colorectal, gastric, glioblastoma, lung, melanoma, ovarian, pancreatic, prostate, renal` — 10 indications, 81 (cancer, gene) rows.

---

## Project layout

```
owkin-agent/
├── README.md
├── Dockerfile
├── compose.yaml
├── .dockerignore
├── .gitignore
├── .env.example
├── requirements.txt
├── pytest.ini
├── data/
│   └── owkin_take_home_data.csv
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app, lifespan, /, /health, /chat (SSE)
│   ├── agent.py           # SYSTEM_PROMPT + run_agent async generator
│   ├── tools.py           # get_targets, get_expressions, TOOL_SCHEMAS, dispatch_tool
│   ├── data.py            # CSV loader + cancer-type helper
│   ├── config.py          # env vars (fail-fast on missing key)
│   ├── static/
│   │   └── chat.js        # vanilla JS chat client (SSE consumer + Markdown rendering)
│   └── templates/
│       └── index.html     # Tailwind via CDN, marked + DOMPurify for Markdown
└── tests/
    ├── __init__.py
    ├── test_tools.py
    └── test_agent.py
```

---

## Quick start

### With Docker Compose (preferred — one command)

```bash
cp .env.example .env       # then put your real ANTHROPIC_API_KEY in .env
docker compose up --build
```

Open http://localhost:8000. Stop with `Ctrl+C`, clean up with `docker compose down`.

### With plain `docker build` / `docker run`

```bash
docker build -t owkin-agent .
docker run --rm -p 8000:8000 --env-file .env owkin-agent
```

### Without Docker

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # add ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

### Running the tests

```bash
pip install -r requirements.txt
pytest
```

---

## Architecture

```
┌────────────┐      POST /chat (JSON)        ┌─────────────────────────────┐
│  Browser   │  ─────────────────────────►   │       FastAPI (uvicorn)     │
│  (vanilla  │  ◄── SSE events ─────────────│  ┌───────────────────────┐  │
│  JS + TW)  │     (text / tool_call /       │  │ in-memory sessions    │  │
└────────────┘      tool_result / done)      │  │   {sid: [messages]}   │  │
                                              │  └───────────┬───────────┘  │
                                              │              ▼              │
                                              │    ┌────────────────────┐   │
                                              │    │   run_agent loop   │◄─┐
                                              │    │ (async generator)  │  │
                                              │    └─────┬────────┬─────┘  │
                                              │          │        │         │
                                              │          ▼        ▼         │
                                              │  ┌──────────┐ ┌────────┐    │
                                              │  │  Async   │ │ pandas │    │
                                              │  │ Anthropic│ │ in-mem │    │
                                              │  │   API    │ │   df   │    │
                                              │  └──────────┘ └────────┘    │
                                              └─────────────────────────────┘
```

Chained-query flow:

```
user: "median expression of genes in breast cancer?"
  └─► Claude → tool_use: get_targets(cancer_name="breast")
        └─► pandas filter → ["BRCA2","BRCA1","TP53",...]
  └─► Claude → tool_use: get_expressions(genes=[...], cancer_name="breast")
        └─► pandas filter (gene ∈ list AND cancer = "breast") → {"BRCA2":0.032,...}
  └─► Claude → end_turn: natural-language summary
```

---

## Deviation from the brief — `get_expressions(genes, cancer_name)`

The brief gives `get_expressions(genes) → dict(zip(...))`. With the real CSV, several genes (TP53 in 8 cancers, KRAS in 5, BRCA1/BRCA2/PIK3CA/CDH1 in multiple) appear in multiple indications — `dict(zip(...))` silently keeps the *last* row in CSV order, returning values from the wrong cancer. For breast: 5/10 contaminated.

**Fix.** Added a required `cancer_name` argument to `get_expressions`. The system prompt instructs the model to pass the same `cancer_name` to both tools when chaining, and the function now filters jointly on `gene ∈ genes` AND `cancer_indication == cancer_name`.


---

## AI components — design and trade-offs

- **Tool use, not RAG.** Dataset is small, fully structured, deterministic. Embedding 81 rows would add latency, cost, and a hallucination surface. Native tool calls are exact, auditable (each call is rendered as a pill in the UI), and composable (the chained query passes one tool's output as the next tool's input).
- **`claude-sonnet-4-6`.** Balances cost and instruction-following for a 2-tool surface. Opus triples the cost with no measurable quality gain on a deterministic problem. Haiku is borderline on multi-step chaining.
- **Sessions.** In-memory `dict[session_id, list[message]]` on `app.state`, keyed by a UUID generated client-side. Wiped on restart, no multi-instance support — acceptable for a POC; Redis/Postgres was a deliberate scope-cut.
- **Streaming.** Server-Sent Events with typed events (`text`, `tool_call`, `tool_result`, `done`, `error`). Frontend uses `fetch` + `ReadableStream`. Backend uses `AsyncAnthropic` natively async — no thread wrapping, the event loop is never blocked.
- **Limitations.** In-memory sessions wiped on restart.

---

## AI-assisted coding — pros and cons

**Pros.** Scaffolding (FastAPI lifespan, SSE plumbing, Jinja2, Docker, the Anthropic tool-use loop boilerplate) is mechanical and the assistant produces it cleanly on the first pass. Saved real time on the parts of the brief that are well-documented patterns.

**Cons.** The default impulse is to **over-complexify** parts of the brief that don't need it: defensive `isinstance` guards in the tool functions, `astype(str)` / `.strip().lower()` on already-clean CSV inputs, fallback branches for things that don't actually fail (`crypto.randomUUID`, missing CDN libs), validation duplicated across layers. Each one looks "robust" but is code the brief never asked for. The final design decisions (no React, in-memory sessions, Sonnet over Opus, native async client, where to draw the line on validation) were judgement calls the assistant has no way to make — and where it tried, it tilted heavily toward more code, not less.

The honest summary: assistants compress the time-to-running-app by 2–3×, but the discipline of saying "no" to plausible-looking complexity is the human's job.
