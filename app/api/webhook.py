import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from loguru import logger

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from sqlmodel import Session, select

from app.core.db import get_session
from app.core.time_utils import now_utc

from app.models.check_result import ServiceConfig

load_dotenv()

# A simple, hardcoded API key for this internal service
API_KEY = os.environ.get("MONAGENT_API_KEY", "MA-HEART-BEAT")


async def heartbeat(request: Request) -> JSONResponse:
    """Receives a heartbeat ping for a service."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON payload"}, status_code=400)

    if payload.get("api_key") != API_KEY:
        return JSONResponse({"error": "Invalid API key"}, status_code=403)

    service_name = payload.get("service_name")
    if not service_name:
        return JSONResponse({"error": "service_name is required"}, status_code=400)

    logger.info(f"💓 Heartbeat received for: {service_name}")

    with get_session() as session:
        statement = select(ServiceConfig).where(ServiceConfig.name == service_name)
        service = session.exec(statement).first()

        if service:
            # Service exists, update its timestamp
            service.last_seen = now_utc()
            session.add(service)
            session.commit()
            return JSONResponse({"status": "updated", "service_name": service_name})
        else:
            # Auto-registration: service does not exist, create it
            new_service = ServiceConfig(
                name=service_name,
                probe_type="heartbeat",
                address="N/A",
                interval_seconds=payload.get("interval_seconds", 60),
                timeout_seconds=payload.get("timeout_seconds", 30),
                alert_threshold=payload.get("alert_threshold", 0),
                last_seen=now_utc(),
            )
            session.add(new_service)
            session.commit()
            return JSONResponse(
                {"status": "created", "service_name": service_name},
                status_code=201,
            )


routes = [
    Route("/api/v1/heartbeat", endpoint=heartbeat, methods=["POST"]),
]

app = Starlette(routes=routes)
