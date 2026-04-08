import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlmodel import Session, select
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.db import get_engine
from app.models.check_result import ServiceConfig

load_dotenv()

API_KEY = os.environ.get("MONAGENT_API_KEY")


async def heartbeat_webhook(request: Request) -> JSONResponse:
    """
    Listen for check-ins from external agents.
    Performs an UPSERT operation on the service config.
    """
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

    if not API_KEY or payload.get("api_key") != API_KEY:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    service_name = payload.get("service_name")
    if not service_name:
        return JSONResponse({"error": "`service_name` is required"}, status_code=400)

    with Session(get_engine()) as session:
        config = session.exec(
            select(ServiceConfig).where(ServiceConfig.name == service_name)
        ).first()

        now = datetime.now(timezone.utc)

        if config:
            # UPDATE
            config.last_seen = now
            if payload.get("interval_seconds"):
                config.interval_seconds = int(payload["interval_seconds"])
            if "alert_threshold" in payload:
                config.alert_threshold = int(payload["alert_threshold"])
            session.add(config)
            session.commit()
            return JSONResponse({"status": "updated", "service": service_name})
        else:
            # CREATE
            new_config = ServiceConfig(
                name=service_name,
                target_url="heartbeat",
                probe_type="heartbeat",
                interval_seconds=int(payload.get("interval_seconds", 3600)),
                alert_threshold=int(payload.get("alert_threshold", 0)),
                last_seen=now,
            )
            session.add(new_config)
            session.commit()
            return JSONResponse({"status": "created", "service": service_name})


routes = [
    Route("/api/v1/heartbeat", endpoint=heartbeat_webhook, methods=["POST"]),
]

app = Starlette(routes=routes)
