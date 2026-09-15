"""
DISTRIBUTED COMPUTING CONCEPT DEMONSTRATION: CENTRAL MONITORING SERVER & CONCURRENT REQUEST HANDLER

Role in Distributed Architecture:
- Central Monitoring Aggregator receiving telemetry from multiple distributed edge nodes.
- Concurrency Model: Built on FastAPI & Uvicorn asynchronous event loop and thread pools.
  It handles concurrent incoming HTTP POST requests from multiple nodes simultaneously without blocking.
- Data Processing: Evaluates telemetry, computes real-time congestion levels, updates central state DB,
  and broadcasts telemetry & alerts to polling visual dashboard clients.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from server.database import (
    init_db,
    record_node_telemetry,
    get_all_junctions,
    get_junction_history,
    get_recent_alerts,
    get_db_connection
)
from server.analytics import calculate_congestion_level, compute_network_summary

# Configure logging to clearly visualize server concurrency and incoming reports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [CentralServer] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("CentralServer")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup & shutdown events. Initializing DB on startup.
    """
    logger.info("🚀 Starting Central Monitoring Server...")
    init_db()
    logger.info("📡 Ready to ingest distributed node telemetry.")
    yield
    logger.info("🛑 Shutting down Central Monitoring Server.")

app = FastAPI(
    title="Distributed Traffic Monitoring Server",
    description="Central aggregator for independent edge traffic monitoring nodes.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS so dashboard clients can connect seamlessly
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic schema for node telemetry reporting
class TelemetryReport(BaseModel):
    junction_id: str = Field(..., json_schema_extra={"example": "J1"}, description="Unique identifier for the road junction")
    junction_name: str = Field(..., json_schema_extra={"example": "North Junction"}, description="Human readable name")
    vehicle_count: int = Field(..., ge=0, json_schema_extra={"example": 45}, description="Number of vehicles detected")
    avg_speed_kmh: float = Field(..., ge=0.0, json_schema_extra={"example": 35.5}, description="Average speed in km/h")
    weather_condition: Optional[str] = Field("Clear", json_schema_extra={"example": "Rainy"})
    timestamp: str = Field(..., description="ISO 8601 timestamp generated at node")
    sequence_num: int = Field(..., description="Monotonically increasing sequence number from node")

# Pydantic schema for simulation trigger
class SurgeTriggerRequest(BaseModel):
    vehicle_count: int = Field(95, ge=50, le=200)
    avg_speed_kmh: float = Field(12.0, ge=1.0, le=30.0)

# ==========================================
# REST API ENDPOINTS FOR DISTRIBUTED NODES & DASHBOARD
# ==========================================

@app.post("/api/report", status_code=status.HTTP_200_OK)
def receive_node_telemetry(report: TelemetryReport):
    """
    CONCURRENT INGESTION ENDPOINT:
    Each distributed node periodically POSTs its telemetry here.
    Handled concurrently by worker threads without blocking other incoming node reports.
    """
    payload = report.dict()
    junction_id = payload["junction_id"]
    count = payload["vehicle_count"]
    speed = payload["avg_speed_kmh"]
    seq = payload["sequence_num"]

    # Calculate real-time localized congestion level based on thresholds
    congestion_level = calculate_congestion_level(count, speed)

    logger.info(
        f"📥 Ingested telemetry from Node '{junction_id}' (Seq #{seq}) | "
        f"Vehicles: {count}, Speed: {speed} km/h -> Congestion: [{congestion_level.upper()}]"
    )

    # Persist to SQLite DB concurrently
    success = record_node_telemetry(payload, congestion_level)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record node telemetry in database."
        )

    return {
        "status": "success",
        "junction_id": junction_id,
        "sequence_num": seq,
        "congestion_level": congestion_level,
        "message": f"Telemetry processed for {junction_id}"
    }

@app.get("/api/status")
def get_system_status():
    """
    DASHBOARD AGGREGATION ENDPOINT:
    Returns the latest state of all registered nodes along with system-wide aggregated metrics.
    """
    junctions = get_all_junctions()
    summary = compute_network_summary(junctions)
    return {
        "summary": summary,
        "junctions": junctions
    }

@app.get("/api/history/{junction_id}")
def get_history(junction_id: str, limit: int = 30):
    """
    TIME-SERIES API:
    Returns historical telemetry records for a specific junction for rendering graphs.
    """
    records = get_junction_history(junction_id, limit=limit)
    return {
        "junction_id": junction_id,
        "record_count": len(records),
        "history": records
    }

@app.get("/api/alerts")
def get_alerts(limit: int = 15):
    """
    ALERTING API:
    Returns recent high-congestion alert events detected by the server.
    """
    alerts = get_recent_alerts(limit=limit)
    return {
        "alert_count": len(alerts),
        "alerts": alerts
    }

@app.post("/api/simulate-surge/{junction_id}")
def simulate_surge(junction_id: str, req: SurgeTriggerRequest):
    """
    INTERACTIVE DEMO FEATURE:
    Injects a heavy traffic spike into a specific node from the dashboard to visually test alerting.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT junction_name, weather_condition FROM junctions WHERE junction_id = ?", (junction_id,))
    row = cursor.fetchone()
    conn.close()

    name = row["junction_name"] if row else f"Junction {junction_id}"
    weather = row["weather_condition"] if row else "Clear"

    fake_payload = {
        "junction_id": junction_id,
        "junction_name": name,
        "vehicle_count": req.vehicle_count,
        "avg_speed_kmh": req.avg_speed_kmh,
        "weather_condition": weather,
        "timestamp": None,
        "sequence_num": 9999
    }

    congestion_level = calculate_congestion_level(req.vehicle_count, req.avg_speed_kmh)
    record_node_telemetry(fake_payload, congestion_level)

    logger.warning(
        f"⚡ MANUALLY SIMULATED TRAFFIC SURGE on Node '{junction_id}': "
        f"{req.vehicle_count} vehicles, {req.avg_speed_kmh} km/h -> {congestion_level}"
    )

    return {
        "status": "surge_simulated",
        "junction_id": junction_id,
        "vehicle_count": req.vehicle_count,
        "avg_speed_kmh": req.avg_speed_kmh,
        "congestion_level": congestion_level
    }

# Mount static files for dashboard frontend
dashboard_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard")
if os.path.exists(dashboard_dir):
    app.mount("/static", StaticFiles(directory=dashboard_dir), name="static")

    @app.get("/")
    def serve_dashboard():
        index_path = os.path.join(dashboard_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {"message": "Dashboard index.html not found"}

if __name__ == "__main__":
    import uvicorn
    # Launch Uvicorn server with multiple worker threads for high concurrency handling
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=True)
