"""
DISTRIBUTED COMPUTING CONCEPT DEMONSTRATION: CENTRALIZED DATA AGGREGATION & ANALYTICS

Role in Distributed Architecture:
- Aggregates distributed telemetry arriving from multiple independent node streams.
- Computes real-time congestion classification (Low, Medium, High) based on localized threshold metrics.
- Derives network-wide global state metrics from discrete localized telemetry reports.
"""

from datetime import datetime, timezone

def calculate_congestion_level(vehicle_count: int, avg_speed_kmh: float) -> str:
    """
    Classifies traffic congestion level based on localized node metrics.
    
    Rules:
    - High Congestion: High vehicle density (>=60 vehicles) OR dangerously low speed (<20 km/h)
    - Medium Congestion: Moderate vehicle density (30 to 59 vehicles) OR slowed speed (20 to 39.9 km/h)
    - Low Congestion: Low vehicle density (<30 vehicles) AND normal flow speed (>=40 km/h)
    """
    if vehicle_count >= 60 or avg_speed_kmh < 20.0:
        return "High"
    elif vehicle_count >= 30 or avg_speed_kmh < 40.0:
        return "Medium"
    else:
        return "Low"

def compute_network_summary(junctions: list) -> dict:
    """
    Computes global system metrics by aggregating data from all active nodes.
    Demonstrates Centralized Aggregation in Distributed Monitoring.
    """
    if not junctions:
        return {
            "total_nodes": 0,
            "active_nodes": 0,
            "total_vehicles": 0,
            "network_avg_speed": 0.0,
            "high_congestion_count": 0,
            "medium_congestion_count": 0,
            "low_congestion_count": 0,
            "overall_status": "IDLE",
            "highest_traffic_junction": "N/A"
        }

    now = datetime.now(timezone.utc)
    active_nodes = 0
    total_vehicles = 0
    sum_speeds = 0.0
    high_count = 0
    med_count = 0
    low_count = 0
    max_vehicles = -1
    highest_junc = "None"

    for j in junctions:
        # Check node liveness (reported within last 20 seconds)
        last_seen_str = j.get("last_seen", "")
        try:
            last_seen_dt = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
            time_diff = (now - last_seen_dt).total_seconds()
            if time_diff <= 20.0:
                active_nodes += 1
        except Exception:
            active_nodes += 1

        v_count = j.get("vehicle_count", 0)
        speed = j.get("avg_speed_kmh", 0.0)
        c_level = j.get("congestion_level", "Low")

        total_vehicles += v_count
        sum_speeds += speed

        if c_level == "High":
            high_count += 1
        elif c_level == "Medium":
            med_count += 1
        else:
            low_count += 1

        if v_count > max_vehicles:
            max_vehicles = v_count
            highest_junc = f"{j.get('junction_name')} ({v_count} veh)"

    avg_speed = round(sum_speeds / len(junctions), 1) if junctions else 0.0

    # Determine overall network health status
    if high_count >= 2 or (len(junctions) > 0 and high_count / len(junctions) >= 0.4):
        overall_status = "HEAVY_CONGESTION"
    elif high_count >= 1 or med_count >= 2:
        overall_status = "MODERATE_TRAFFIC"
    else:
        overall_status = "SMOOTH_FLOW"

    return {
        "total_nodes": len(junctions),
        "active_nodes": active_nodes,
        "total_vehicles": total_vehicles,
        "network_avg_speed": avg_speed,
        "high_congestion_count": high_count,
        "medium_congestion_count": med_count,
        "low_congestion_count": low_count,
        "overall_status": overall_status,
        "highest_traffic_junction": highest_junc
    }
