import uvicorn
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from loguru import logger
from sqlmodel import select
from app.core.db import get_session, init_db
from app.models.check_result import CheckResult, ServiceConfig

# Definitive FastAPI instance
app = FastAPI(title="monagent API")


class HeartbeatPayload(BaseModel):
    service_name: str


@app.get("/")
async def health():
    return {"status": "online", "port": 8001}


@app.post("/webhook/heartbeat")
async def receive_heartbeat(request: Request, payload: HeartbeatPayload):
    srv_name = str(payload.service_name)

    # Extract client IP address
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"💓 Heartbeat received for: {srv_name} from IP: {client_ip}")

    try:
        with get_session() as session:
            statement = select(ServiceConfig).where(ServiceConfig.name == srv_name)
            config = session.exec(statement).first()

            if not config:
                logger.warning(f"⚠️ Service '{srv_name}' not found.")
                raise HTTPException(status_code=404, detail="Service not found")

            # Update last_seen (naive UTC for SQLite)
            config.last_seen = datetime.now(timezone.utc).replace(tzinfo=None)
            session.add(config)
            session.commit()

            # Create CheckResult entry with source IP
            result = CheckResult(
                service_name=srv_name,
                is_healthy=True,
                latency_ms=0.0,
                status_code=None,
                error_message=None,
                extra_info={
                    "source_ip": client_ip,
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                },
            )
            session.add(result)
            session.commit()

            logger.success(f"✅ Updated {srv_name} (IP: {client_ip})")
            return {"status": "ok", "source_ip": client_ip}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def start_server():
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")


if __name__ == "__main__":
    start_server()
