"""
DISTRIBUTED COMPUTING CONCEPT DEMONSTRATION: INDEPENDENT AUTONOMOUS NODE SIMULATOR

Role in Distributed Architecture:
- Represents an edge device / IoT traffic monitoring camera placed at a specific road junction.
- Runs as an independent process (or Docker container) isolated from other nodes and the central server.
- Operates autonomously: senses local state, generates telemetry, and pushes updates periodically.
- Demonstrates Fault Tolerance: gracefully handles network failures and server down-time with retries.
"""

import argparse
import json
import logging
import random
import time
from datetime import datetime, timezone
import requests

# Configure logging to clearly demonstrate node activity in stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [Node-%(junction_id)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Custom Logger Adapter to inject junction_id into log records
class NodeLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        kwargs["extra"] = {"junction_id": self.extra["junction_id"]}
        return msg, kwargs

class TrafficNodeSimulator:
    """
    Simulates a smart traffic monitoring camera node.
    Calculates vehicle count, average speed, and weather condition for a given junction.
    """
    WEATHER_TYPES = ["Clear", "Rainy", "Foggy", "Overcast"]

    def __init__(self, junction_id: str, name: str, server_url: str, interval: float = 3.0):
        self.junction_id = junction_id
        self.name = name
        self.server_url = server_url.rstrip("/")
        self.report_endpoint = f"{self.server_url}/api/report"
        self.interval = interval
        self.sequence_num = 0
        
        # Base traffic simulation variables (vary per node to create realistic heterogeneity)
        # Using hash of junction_id for deterministic baseline diversity
        seed = sum(ord(c) for c in junction_id)
        random.seed(seed + int(time.time()) % 100)
        self.base_vehicle_count = random.randint(15, 45)
        self.base_avg_speed = random.uniform(35.0, 65.0)
        self.weather = random.choice(self.WEATHER_TYPES)
        
        # Surge state (simulates accidents or congestion spikes)
        self.is_surge_active = False
        self.surge_ticks_left = 0

        logger = logging.getLogger("TrafficNode")
        self.logger = NodeLoggerAdapter(logger, {"junction_id": self.junction_id})

    def generate_telemetry(self) -> dict:
        """
        Simulates physical sensor reading at the edge node.
        Includes stochastic variations and occasional congestion spikes.
        """
        self.sequence_num += 1

        # Randomly toggle surge condition (5% chance if not active)
        if not self.is_surge_active and random.random() < 0.05:
            self.is_surge_active = True
            self.surge_ticks_left = random.randint(4, 10)
            self.logger.info("⚠️ Traffic surge initiated locally (accidents/bottleneck detected at edge)")

        if self.is_surge_active:
            # High vehicle count, low speed during a surge
            vehicle_count = random.randint(65, 110)
            avg_speed = round(random.uniform(5.0, 18.0), 1)
            self.surge_ticks_left -= 1
            if self.surge_ticks_left <= 0:
                self.is_surge_active = False
                self.logger.info("✅ Traffic surge cleared. Returning to normal traffic flow.")
        else:
            # Normal traffic fluctuations
            count_delta = random.randint(-8, 8)
            speed_delta = random.uniform(-4.0, 4.0)
            vehicle_count = max(5, self.base_vehicle_count + count_delta)
            avg_speed = round(max(10.0, min(90.0, self.base_avg_speed + speed_delta)), 1)

        # Weather changes occasionally
        if random.random() < 0.02:
            self.weather = random.choice(self.WEATHER_TYPES)

        payload = {
            "junction_id": self.junction_id,
            "junction_name": self.name,
            "vehicle_count": vehicle_count,
            "avg_speed_kmh": avg_speed,
            "weather_condition": self.weather,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sequence_num": self.sequence_num
        }
        return payload

    def send_report(self, payload: dict) -> bool:
        """
        Transmits telemetry payload to central monitoring server via REST API (HTTP POST).
        Demonstrates Fault Tolerance with retry & backoff mechanism.
        """
        max_retries = 3
        backoff = 1.0

        for attempt in range(1, max_retries + 1):
            try:
                start_time = time.time()
                response = requests.post(
                    self.report_endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=4.0
                )
                latency_ms = round((time.time() - start_time) * 1000, 1)

                if response.status_code in (200, 201):
                    res_json = response.json()
                    congestion = res_json.get("congestion_level", "Unknown")
                    self.logger.info(
                        f"📤 Reported Seq #{payload['sequence_num']} -> "
                        f"Vehicles: {payload['vehicle_count']}, Speed: {payload['avg_speed_kmh']} km/h | "
                        f"Server Response: {response.status_code} OK (Congestion: {congestion}, Latency: {latency_ms}ms)"
                    )
                    return True
                else:
                    self.logger.warning(
                        f"⚠️ Server returned HTTP {response.status_code}: {response.text} (Attempt {attempt}/{max_retries})"
                    )

            except requests.exceptions.RequestException as err:
                self.logger.error(
                    f"❌ Connection error sending data to {self.report_endpoint}: {err} (Attempt {attempt}/{max_retries})"
                )

            if attempt < max_retries:
                time.sleep(backoff)
                backoff *= 2.0

        self.logger.critical("🛑 Failed to report telemetry after maximum retries. Retrying in next cycle.")
        return False

    def run(self):
        """
        Main execution loop of the autonomous node.
        """
        self.logger.info(
            f"🚀 Initializing Edge Node: ID='{self.junction_id}', Name='{self.name}' | "
            f"Target Server='{self.server_url}', Interval={self.interval}s"
        )
        self.logger.info("📡 Starting distributed monitoring transmission loop...")

        try:
            while True:
                payload = self.generate_telemetry()
                self.send_report(payload)
                time.sleep(self.interval)
        except KeyboardInterrupt:
            self.logger.info("🛑 Node simulation stopped by user.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Distributed Traffic Monitoring Node Simulator")
    parser.add_argument("--junction-id", type=str, default="J1", help="Unique identifier for road junction (e.g. J1, J2)")
    parser.add_argument("--name", type=str, default="North Junction", help="Human readable junction name")
    parser.add_argument("--server-url", type=str, default="http://localhost:8000", help="Central monitoring server URL")
    parser.add_argument("--interval", type=float, default=3.0, help="Reporting frequency in seconds")

    args = parser.parse_args()

    node = TrafficNodeSimulator(
        junction_id=args.junction_id,
        name=args.name,
        server_url=args.server_url,
        interval=args.interval
    )
    node.run()
