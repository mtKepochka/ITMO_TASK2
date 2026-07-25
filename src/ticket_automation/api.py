from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import __version__
from .audit import JsonlAudit
from .models import ProcessingResult, Ticket
from .pipeline import PROJECT_ROOT, TicketPipeline
from .retrieval import LexicalRetriever


class TicketRequest(BaseModel):
    ticket_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=20_000)
    subject: str = Field(default="", max_length=500)
    channel: Literal["chat", "email", "web", "mobile"] = "web"
    simulate_component_failure: Literal["classification", "risk"] | None = None
    simulate_component_timeout: Literal["classification", "risk"] | None = None


class RuntimeMetrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self.started_at = time.time()
        self.requests = 0
        self.actions: dict[str, int] = {}
        self.fast_path_total_ms = 0.0
        self.technical_fallbacks = 0

    def observe(self, result: ProcessingResult) -> None:
        with self._lock:
            action = result.decision.action
            self.requests += 1
            self.actions[action] = self.actions.get(action, 0) + 1
            self.fast_path_total_ms += result.fast_path_ms
            self.technical_fallbacks += int(bool(result.technical_errors))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            average = (
                self.fast_path_total_ms / self.requests
                if self.requests
                else 0.0
            )
            return {
                "status": "ok",
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "requests": self.requests,
                "actions": dict(sorted(self.actions.items())),
                "average_fast_path_ms": round(average, 3),
                "technical_fallbacks": self.technical_fallbacks,
            }


DASHBOARD = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Ticket Automation Control Center</title>
  <style>
    body { font: 16px/1.45 system-ui,sans-serif; max-width: 960px; margin: 40px auto; padding: 0 20px; }
    textarea,input,select,button { box-sizing: border-box; font: inherit; padding: 10px; }
    textarea,input { width: 100%; margin: 6px 0 14px; }
    textarea { min-height: 120px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    button { cursor: pointer; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; padding: 16px; border: 1px solid currentColor; }
    .trace { display: grid; grid-template-columns: repeat(auto-fit,minmax(170px,1fr)); gap: 10px; margin: 20px 0; }
    .trace div { border: 1px solid currentColor; padding: 12px; }
  </style>
</head>
<body>
  <h1>Ticket Automation Control Center</h1>
  <p>По умолчанию система готовит подсказку оператору. Автоответ требует отдельной rollout-конфигурации.</p>
  <form id="ticket-form">
    <div class="row">
      <label>Ticket ID<input id="ticket-id" value="dashboard-1" required></label>
      <label>Канал<select id="channel"><option>web</option><option>chat</option><option>email</option><option>mobile</option></select></label>
    </div>
    <label>Тема<input id="subject" value="Проблема с приложением"></label>
    <label>Обращение<textarea id="text" required>Приложение не открывается. Это общий сбой?</textarea></label>
    <button>Обработать</button>
  </form>
  <div class="trace" id="trace"></div>
  <pre id="result">Результат появится здесь.</pre>
  <script>
    const form = document.querySelector("#ticket-form");
    form.addEventListener("submit", async event => {
      event.preventDefault();
      const response = await fetch("/api/v1/tickets/process", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          ticket_id: document.querySelector("#ticket-id").value,
          subject: document.querySelector("#subject").value,
          text: document.querySelector("#text").value,
          channel: document.querySelector("#channel").value
        })
      });
      const payload = await response.json();
      document.querySelector("#result").textContent = JSON.stringify(payload, null, 2);
      const value = payload.result || {};
      document.querySelector("#trace").innerHTML = [
        ["Классификация", `${value.category || "—"} (${value.confidence ?? "—"})`],
        ["Риск", value.risk_level || "—"],
        ["База знаний", value.retrieval?.article_id || "не найдена"],
        ["Решение", value.action || "—"],
        ["Rollout", value.rollout_version || "—"]
      ].map(([name, detail]) => `<div><strong>${name}</strong><br>${detail}</div>`).join("");
    });
  </script>
</body>
</html>
"""


def create_app(
    *,
    project_root: Path = PROJECT_ROOT,
    audit_path: str | Path | None = None,
    rollout_path: str | Path | None = None,
    fast_path_deadline_ms: int | None = None,
) -> FastAPI:
    effective_audit = Path(
        audit_path
        or os.getenv(
            "TICKET_AUDIT_PATH",
            project_root / "audit" / "decisions.jsonl",
        )
    )
    effective_rollout = Path(
        rollout_path
        or os.getenv(
            "TICKET_ROLLOUT_CONFIG",
            project_root / "config" / "rollout.json",
        )
    )
    deadline = fast_path_deadline_ms or int(
        os.getenv("TICKET_FAST_PATH_DEADLINE_MS", "500")
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.pipeline = TicketPipeline(
            audit=JsonlAudit(effective_audit),
            retriever=LexicalRetriever.from_file(
                project_root / "data" / "knowledge_base.json"
            ),
            rollout_path=effective_rollout,
            fast_path_deadline_ms=deadline,
        )
        app.state.metrics = RuntimeMetrics()
        yield
        app.state.pipeline.close()

    application = FastAPI(
        title="Ticket Automation PoC",
        version=__version__,
        description="Risk-aware support ticket routing and response suggestion.",
        lifespan=lifespan,
    )

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def dashboard() -> HTMLResponse:
        return HTMLResponse(DASHBOARD)

    @application.get("/api/v1/health", tags=["operations"])
    def health(request: Request) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "rollout_version": request.app.state.pipeline.rollout.version,
        }

    @application.get("/api/v1/metrics", tags=["operations"])
    def metrics(request: Request) -> dict[str, Any]:
        return request.app.state.metrics.snapshot()

    @application.post("/api/v1/tickets/process", tags=["tickets"])
    def process_ticket(
        payload: TicketRequest,
        request: Request,
    ) -> dict[str, Any]:
        ticket = Ticket(
            id=payload.ticket_id,
            channel=payload.channel,
            subject=payload.subject,
            text=payload.text,
            created_at=datetime.now(UTC).isoformat(),
        )
        result = request.app.state.pipeline.process(
            ticket,
            simulate_component_failure=payload.simulate_component_failure,
            simulate_component_timeout=payload.simulate_component_timeout,
        )
        request.app.state.metrics.observe(result)
        return {"result": result.to_dict()}

    @application.get("/api/v1/tickets/{ticket_id}", tags=["tickets"])
    def get_ticket(ticket_id: str, request: Request) -> dict[str, Any]:
        result = request.app.state.pipeline.get_result(ticket_id)
        if result is None:
            raise HTTPException(status_code=404, detail="ticket not found")
        return {"result": result.to_dict()}

    return application


app = create_app()


def run() -> None:
    uvicorn.run(
        "ticket_automation.api:app",
        host=os.getenv("TICKET_API_HOST", "127.0.0.1"),
        port=int(os.getenv("TICKET_API_PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    run()
