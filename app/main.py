import json
from contextlib import asynccontextmanager
from pathlib import Path

from anthropic import Anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .agent import run_agent
from .config import load_settings
from .data import get_available_cancer_types, load_dataframe

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    df = load_dataframe(settings.csv_path)
    client = Anthropic(api_key=settings.anthropic_api_key)

    app.state.settings = settings
    app.state.df = df
    app.state.client = client
    app.state.cancer_types = get_available_cancer_types(df)
    app.state.sessions = {}
    yield


app = FastAPI(title="Owkin Agent POC", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class ChatRequest(BaseModel):
    session_id: str
    message: str


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(request: Request, body: ChatRequest):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message must be non-empty")

    sessions: dict = request.app.state.sessions
    history = sessions.setdefault(body.session_id, [])
    history.append({"role": "user", "content": body.message})

    settings = request.app.state.settings
    df = request.app.state.df
    client = request.app.state.client
    cancer_types = request.app.state.cancer_types

    async def event_stream():
        try:
            async for event in run_agent(
                history,
                df,
                client,
                model_name=settings.model_name,
                cancer_types=cancer_types,
                max_tool_iterations=settings.max_tool_iterations,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:  # noqa: BLE001 — surface to UI
            err = {"type": "error", "content": f"agent failed: {exc!s}"}
            yield f"data: {json.dumps(err)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
