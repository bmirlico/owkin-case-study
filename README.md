# Owkin Agent POC

A 4-hour proof of concept for the Owkin Forward Deployed Engineer take-home: a small web application where a non-technical user asks natural-language questions about a cancer-genomics dataset, and an LLM agent orchestrates two existing Python functions over a CSV to answer.

---

## What it does

The app exposes a chat UI in the browser. The user types a question; the backend forwards it to Claude (`claude-sonnet-4-6`) using the **Anthropic native tool-use API**, with two tools registered:

- `get_targets(cancer_name)` — list of genes for a cancer indication.
- `get_expressions(genes)` — `{gene: median_value}` for a list of genes.

The model decides whether to call a tool, which one, and — for the chained queries — whether to call them in sequence. Tool results are fed back into the conversation; the model produces a final natural-language answer.

### Reference queries supported

| # | User query | Behaviour |
|---|------------|-----------|
| 1 | *How can you help me?* | Plain text answer describing capabilities and the available cancer indications. No tool calls. |
| 2 | *What are the main genes involved in lung cancer?* | One tool call: `get_targets("lung")` → answer with the gene list. |
| 3 | *What is the median value expression of genes involved in breast cancer?* | **Chained**: `get_targets("breast")` → `get_expressions([...])` → answer. |
| 4 | *What is the median value expression of genes involved in esophageal cancer?* | The dataset doesn't include esophageal — the model says so explicitly and lists the 10 indications it does cover, **without inventing data**. |

The chaining in query 3 is the agentic behaviour: the model — not the application code — decides to call `get_targets` first, read the returned list, then call `get_expressions` with it.

Query 4 happens to be a useful demonstration of the *opposite* signal: when asked about a cancer that isn't in the dataset, the model refuses to call any tool and instead lists the available indications. This is driven by the system prompt's enumeration of valid cancer types and the explicit instruction not to invent values.

### Sample output (query 3 against the real CSV)

```
🔧 get_targets({"cancer_name":"breast"})
↳ get_targets → ["BRCA2","BRCA1","TP53","GATA3","CDH1","ESR1","MAP3K1","HER2","PIK3CA","AKT1"]
🔧 get_expressions({"genes":["BRCA2","BRCA1","TP53","GATA3","CDH1","ESR1","MAP3K1","HER2","PIK3CA","AKT1"], "cancer_name":"breast"})
↳ get_expressions → {"BRCA2":0.032,"BRCA1":0.094,"TP53":0.233,"GATA3":0.602,"CDH1":0.561,"ESR1":0.716,"MAP3K1":0.701,"HER2":0.42,"PIK3CA":0.449,"AKT1":0.278}

| Gene   | Median Expression |
|--------|-------------------|
| BRCA2  | 0.032 |
| BRCA1  | 0.094 |
| TP53   | 0.233 |
| GATA3  | 0.602 |
| CDH1   | 0.561 |
| ESR1   | 0.716 |
| MAP3K1 | 0.701 |
| HER2   | 0.420 |
| PIK3CA | 0.449 |
| AKT1   | 0.278 |
```

### Available cancer indications (from the bundled CSV)

`breast, colorectal, gastric, glioblastoma, lung, melanoma, ovarian, pancreatic, prostate, renal` — 10 indications, 81 (cancer, gene) rows.

---

## Quick start

### With Docker Compose (preferred — one command)

```bash
cp .env.example .env       # then put your real ANTHROPIC_API_KEY in .env
docker compose up --build
```

Open http://localhost:8000. Stop with `Ctrl+C`, clean up with `docker compose down`.

The `compose.yaml` wires the `Dockerfile` build, the `.env` injection, and the
`8000:8000` port mapping in one place so the panel doesn't have to remember flags.

### With plain `docker build` / `docker run`

Same result, useful if you want to see the Docker primitives Compose wraps:

```bash
docker build -t owkin-agent .
docker run --rm -p 8000:8000 --env-file .env owkin-agent
```

### Without Docker (fastest dev loop)

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

The CSV (`data/owkin_take_home_data.csv`) is the file provided with the brief — schema `cancer_indication, gene, median_value`, 10 cancer indications, 81 rows.

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
                                              │  │ Anthropic│ │ pandas │    │
                                              │  │ Messages │ │ in-mem │    │
                                              │  │   API    │ │   df   │    │
                                              │  └──────────┘ └────────┘    │
                                              └─────────────────────────────┘
```

Chained-query flow (queries 3 and 4):

```
user: "median expression of genes in breast cancer?"
  └─► Claude → tool_use: get_targets(cancer_name="breast")
        └─► pandas filter → ["BRCA2","BRCA1","TP53",...]
  └─► Claude → tool_use: get_expressions(genes=[...], cancer_name="breast")
        └─► pandas filter (gene ∈ list AND cancer = "breast") → {"BRCA2":0.032,...}
  └─► Claude → end_turn: natural-language summary
```

### Project layout

```
owkin-agent/
├── README.md
├── Dockerfile
├── compose.yaml           # one-command run: `docker compose up --build`
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
│   └── templates/
│       └── index.html     # Tailwind CDN, vanilla JS chat
└── tests/
    ├── __init__.py
    ├── test_tools.py
    └── test_agent.py
```

---

## Deviation from the brief — `get_expressions(genes, cancer_name)`

The brief provides this reference function:

```python
def get_expressions(genes: List[str]) -> Dict[str, float]:
    subset = df[df['gene'].isin(genes)]
    return dict(zip(subset['gene'], subset['median_value']))
```

Looks innocuous, but with the real CSV it returns **wrong values** for any gene that appears in more than one cancer indication (which is most of the interesting ones — TP53 is in 8 cancers, KRAS in 5, BRCA1/BRCA2/PIK3CA/CDH1 in multiple). The reason is two compounding bugs:

1. `df[df['gene'].isin(genes)]` filters by gene only — the cancer context from the preceding `get_targets` call is *lost* between the two function calls (the chain only passes the gene list, not the cancer it came from).
2. `dict(zip(...))` over a subset with duplicate keys silently keeps **only the last occurrence** in CSV order, so values for breast genes get overwritten by values from cancers that come later in the file.

Concrete example before the fix, for *"median expression of genes involved in breast cancer"*:

| Gene  | Expected (breast) | Returned | Source row in CSV |
|-------|-------------------|----------|-------------------|
| BRCA2 | 0.032             | 0.112    | pancreatic        |
| BRCA1 | 0.094             | 0.158    | ovarian           |
| TP53  | 0.233             | 0.373    | renal             |
| CDH1  | 0.561             | 0.834    | gastric           |
| PIK3CA| 0.449             | 0.762    | ovarian           |

5 values out of 10 contaminated. The agentic chain itself (`get_targets` → `get_expressions`) was working correctly — the bug is in the second function's contract.

**Fix.** Added `cancer_name: str` as a required argument to `get_expressions`, and the system prompt instructs the model to pass the same `cancer_name` to both tools when chaining. The function then filters jointly on `gene ∈ genes` AND `cancer_indication == cancer_name`, removing the ambiguity at the source.

This is a deliberate departure from the brief's literal signature. The alternative would have been to keep the broken signature and document the bug in the README, which I considered (it's a great panel-discussion topic) — but for an FDE deliverable I'd rather ship a demo that returns *correct* values to a clinician and own the deviation. The reference function is a clear case of an under-specified contract that breaks on real data; calling it out and fixing it is part of the FDE job.

### Note on the query "median value expression of genes…"

The phrasing in queries 3 and 4 is ambiguous: it can mean either *(a)* "for each gene, its median expression value" → a per-gene dict, or *(b)* "the median (one number) across the gene-level expression values" → a scalar. I went with interpretation *(a)* because:

- The CSV column is already called `median_value` — each row stores a precomputed median (presumably across patients). "Median value expression" describes what the column is, not an aggregation to apply.
- The brief's reference signature returns `Dict[str, float]`, not `float`.
- Per-gene is more useful clinically: a biologist wants to see each gene labelled, not a scalar that mixes BRCA1 with HER2.

## AI components — design and trade-offs

### Why tool use, not RAG

The dataset is small, fully structured, and fits in memory. The two operations the user can perform on it are finite, named, and deterministic. **Anthropic's native tool-use is a much better fit than retrieval-augmented generation here:**

- **Determinism.** `get_targets("lung")` is a pandas filter. The result is exact every time. Embedding the CSV and retrieving rows by similarity would re-introduce a hallucination surface (wrong gene picked because of a near-neighbour vector match) for no gain.
- **Latency and cost.** No embedding model in the request path. No vector store to provision. The whole stack is one model call (or two, for chained queries) plus a millisecond pandas lookup.
- **Composability.** Tool calls compose naturally: the model receives a JSON list from `get_targets` and passes it as the `genes` argument to `get_expressions`. With RAG you'd be cramming serialised gene lists into the prompt and hoping the model parses them back out cleanly.
- **Auditability.** Every tool call and result is visible in the chat UI as a pill. A reviewer can see exactly which functions were invoked with which arguments — the kind of trace a clinical/regulated context needs.

### Why `claude-sonnet-4-6` (and not Opus or Haiku)

- **Sonnet 4.6** balances cost and instruction-following for a small tool surface. The system prompt is short, the schemas are simple, and chaining two tools is well within Sonnet's capability.
- **Opus** would roughly triple the cost without measurable quality gain on a 2-tool, deterministic problem. Reserving Opus for cases where reasoning depth is the bottleneck.
- **Haiku** is borderline on multi-step tool chaining when the system prompt has explicit "first do X, then do Y" instructions. Risk of skipping `get_targets` and inventing gene names.

### Sessions and state

In-memory `dict[session_id, list[message]]` on `app.state`. Each browser tab gets a fresh UUID. Trade-off: **wiped on restart, no multi-instance support**. For a 4-hour POC this is the right call — adding Redis or Postgres would burn time on plumbing the panel didn't ask about.

### Streaming

The app streams agent events to the browser as Server-Sent Events. We use `fetch` + `ReadableStream` (not `EventSource`) so we can POST a JSON body. Events are typed (`text`, `tool_call`, `tool_result`, `done`, `error`) so the UI can render tool calls as pills inline with the bubble.

The Anthropic SDK call itself is synchronous; we wrap it in `asyncio.to_thread` so it doesn't block the event loop. We do **not** use the SDK's token-level streaming — for a 4-tool-call max conversation, the latency win wasn't worth the extra parsing.

### Limitations

- **In-memory sessions** wiped on restart and not shared across replicas.
- **Hard API dependency.** No offline mode; no local fallback model.
- **Hallucinated cancer names** mitigated (not eliminated) by enumerating valid indications in the system prompt and lower-casing inputs in `get_targets`. A hostile prompt could still elicit a confident-sounding wrong answer if the model ignores the rules.
- **No auth, no rate limiting, no observability** beyond stdout logs. See *Out of scope*.

---

## AI-assisted coding — pros and cons in this case

**Pros (specific to this build).**
- Scaffolding the FastAPI app + lifespan + Jinja2 + SSE plumbing was fast — boring, well-trodden boilerplate that an assistant generates correctly on the first pass.
- The Anthropic tool-use loop (assistant message → `tool_use` block → tool result → re-call) is a documented pattern; an assistant produces the message-list shape correctly without the repeated trips to the SDK docs you'd otherwise make.
- Test scaffolding (mock `Message`, mock `ToolUseBlock`, `side_effect` returning a sequence) is the kind of mechanical work where assistants shine.

**Cons (specific to this build).**
- The default suggestions tilt toward over-engineering: assistants reflexively reach for LangChain, LlamaIndex, embeddings, vector stores, even on a 33-row dataset with 2 deterministic functions. Every one of those would have been wasted complexity here. Had to override these defaults explicitly.
- Tool-schema details (`input_schema` shape, exact field names the SDK expects, the `tool_result` content-block format) are easy to get subtly wrong; I verified against the SDK's own types rather than trusting generated schemas blindly.
- Final design decisions — *no React*, *in-memory sessions*, *Sonnet over Opus*, *no streaming tokens* — were judgement calls about scope and trade-offs that the assistant has no way to make. It's a fast typist, not a product owner.

The honest summary: assistants compressed the time-to-first-running-app by maybe 2–3×, but the architecture decisions and the discipline of saying "no" to plausible-looking complexity were the human's job.

---

## Out of scope (deliberately)

Mentioned so the panel knows these were considered, not forgotten:

- **Auth / multi-user isolation.** Anyone with the URL can chat. Sessions aren't authenticated.
- **Rate limiting.** A user could spam the endpoint and rack up API cost.
- **Persistence.** Sessions evaporate on restart; nothing is logged to disk.
- **Observability.** No OTEL traces, no metrics, no structured logs — only what uvicorn prints by default.
- **Production-grade prompt-injection defence.** A user could try to talk the model out of using its tools; we rely on the system prompt and don't sanitise.
- **Schema drift handling.** If the CSV's columns change, we fail at startup — by design, but no auto-discovery.
