"""
Seed MongoDB with dummy data for all HelloGard collections.
Run: python -m scripts.seed_dummy_data  (from gard-backend/)
Or:  cd gard-backend && python scripts/seed_dummy_data.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load env
load_dotenv()

MONGODB_URI = os.getenv("Mongodb_URI", "")
DATABASE_NAME = os.getenv("Databse_name", "nbc").strip()

if not MONGODB_URI:
    print("ERROR: Mongodb_URI not set in .env")
    sys.exit(1)


# ─────────────────────────────────────────────
# 1. CALLS (Post-Call Intelligence Agent output)
# ─────────────────────────────────────────────
CALLS = [
    {
        "call_id": "SP50-8801",
        "session_id": "SP50-8801",
        "duration_seconds": 142,
        "outcome": "resolved",
        "primary_topic": "robot_fails_to_charge",
        "secondary_topics": ["charging_station_setup"],
        "agents_activated": ["troubleshooting"],
        "issue_resolved": True,
        "robot_model": "SP50",
        "sentiment": {"start": "frustrated", "end": "positive", "shift": "negative_to_positive"},
        "predicted_csat": 4,
        "actual_csat": 5,
        "follow_up_needed": False,
        "follow_up_action": None,
        "summary": "Customer reported SP50 robotic scrubber had a flashing red light. AI diagnosed a stuck collision bumper. Resolved by removing cardboard wedged in the bumper.",
        "tags": ["charging", "bumper", "resolved", "sp50"],
        "escalation_reason": None,
        "customer_sentiment": "Positive",
        "csat_score": 5,
        "product": "sp50",
        "processed_at": (datetime.now() - timedelta(hours=2)).isoformat(),
        "transcript": [
            {"role": "agent", "content": "Hello, this is HelloGard Technical Support. Are you calling regarding the SP50 floor scrubber?", "timestamp": (datetime.now() - timedelta(hours=2, minutes=2)).isoformat()},
            {"role": "user", "content": "Yes, the red light is flashing and it won't move.", "timestamp": (datetime.now() - timedelta(hours=2, minutes=1, seconds=45)).isoformat()},
            {"role": "agent", "content": "I see. Usually a flashing red light on the SP50 indicates the collision bumper is stuck. Could you please physically press and release the front rubber bumper on the left and right sides to ensure it springs back freely?", "timestamp": (datetime.now() - timedelta(hours=2, minutes=1, seconds=20)).isoformat()},
            {"role": "user", "content": "Oh, wait. Yeah, a piece of cardboard was wedged in the bumper. I pulled it out and the light went green!", "timestamp": (datetime.now() - timedelta(hours=2, minutes=0, seconds=40)).isoformat()},
            {"role": "agent", "content": "Excellent. I'm glad we could resolve that quickly. Is there anything else you need assistance with today?", "timestamp": (datetime.now() - timedelta(hours=2, minutes=0, seconds=10)).isoformat()},
        ],
    },
    {
        "call_id": "W3-3392",
        "session_id": "W3-3392",
        "duration_seconds": 305,
        "outcome": "resolved",
        "primary_topic": "operation_how_to",
        "secondary_topics": ["product_specs"],
        "agents_activated": ["product_knowledge"],
        "issue_resolved": True,
        "robot_model": "W3",
        "sentiment": {"start": "neutral", "end": "positive", "shift": "stable_positive"},
        "predicted_csat": 4,
        "actual_csat": 4,
        "follow_up_needed": False,
        "follow_up_action": None,
        "summary": "User confused how to map a new area for Keenon W3 delivery robot. AI walked them through the touchscreen menu and map scanning procedure.",
        "tags": ["mapping", "setup", "resolved", "w3"],
        "escalation_reason": None,
        "customer_sentiment": "Neutral",
        "csat_score": 4,
        "product": "w3",
        "processed_at": (datetime.now() - timedelta(hours=4)).isoformat(),
        "transcript": [
            {"role": "agent", "content": "Hello, I'm GARD. How can I help you with your robot today?", "timestamp": (datetime.now() - timedelta(hours=4, minutes=5)).isoformat()},
            {"role": "user", "content": "I need to map a new delivery route for my W3 robot.", "timestamp": (datetime.now() - timedelta(hours=4, minutes=4, seconds=40)).isoformat()},
            {"role": "agent", "content": "I can help with that. On the W3 touchscreen, go to Settings > Map Management > Create New Map. Then tap 'Start Scanning' and slowly walk the robot through the delivery area.", "timestamp": (datetime.now() - timedelta(hours=4, minutes=4)).isoformat()},
            {"role": "user", "content": "Got it, the scanning started. How long does it usually take?", "timestamp": (datetime.now() - timedelta(hours=4, minutes=2)).isoformat()},
            {"role": "agent", "content": "For a typical restaurant floor, about 5-10 minutes. Make sure to cover all pathways and the docking station location. The robot will beep when the map is complete.", "timestamp": (datetime.now() - timedelta(hours=4, minutes=1, seconds=30)).isoformat()},
        ],
    },
    {
        "call_id": "V3-1099",
        "session_id": "V3-1099",
        "duration_seconds": 85,
        "outcome": "escalated",
        "primary_topic": "other",
        "secondary_topics": ["display_malfunction"],
        "agents_activated": ["troubleshooting"],
        "issue_resolved": False,
        "robot_model": "V3",
        "sentiment": {"start": "frustrated", "end": "neutral", "shift": "stable"},
        "predicted_csat": 2,
        "actual_csat": None,
        "follow_up_needed": True,
        "follow_up_action": "schedule_technician_visit",
        "summary": "Screen frozen entirely on temi V3. Standard reset not working. Escalated to human support for hardware diagnosis.",
        "tags": ["screen", "frozen", "escalated", "v3"],
        "escalation_reason": "Hardware failure — screen unresponsive after multiple resets",
        "customer_sentiment": "Negative",
        "product": "v3",
        "processed_at": (datetime.now() - timedelta(hours=6)).isoformat(),
        "transcript": [
            {"role": "agent", "content": "Hello, I'm GARD. How can I help you today?", "timestamp": (datetime.now() - timedelta(hours=6, minutes=1, seconds=25)).isoformat()},
            {"role": "user", "content": "My temi V3 screen is completely frozen. Nothing responds.", "timestamp": (datetime.now() - timedelta(hours=6, minutes=1, seconds=10)).isoformat()},
            {"role": "agent", "content": "I understand that's frustrating. Let's try a hard reset. Press and hold the power button for 10 seconds until you see the screen go black.", "timestamp": (datetime.now() - timedelta(hours=6, minutes=0, seconds=50)).isoformat()},
            {"role": "user", "content": "I've tried that three times already. Still frozen.", "timestamp": (datetime.now() - timedelta(hours=6, minutes=0, seconds=30)).isoformat()},
            {"role": "agent", "content": "I see. This may require hands-on diagnosis. Let me connect you with our support team to arrange a technician visit.", "timestamp": (datetime.now() - timedelta(hours=6, minutes=0, seconds=10)).isoformat()},
        ],
    },
    {
        "call_id": "SP50-4421",
        "session_id": "SP50-4421",
        "duration_seconds": 210,
        "outcome": "resolved",
        "primary_topic": "roller_brush_maintenance",
        "secondary_topics": ["general_maintenance"],
        "agents_activated": ["maintenance"],
        "issue_resolved": True,
        "robot_model": "SP50",
        "sentiment": {"start": "neutral", "end": "positive", "shift": "stable_positive"},
        "predicted_csat": 5,
        "actual_csat": 5,
        "follow_up_needed": False,
        "follow_up_action": None,
        "summary": "Caller needed guidance replacing the roller brush on SP50. AI walked through the full procedure step by step. Caller confirmed successful replacement.",
        "tags": ["roller_brush", "maintenance", "replacement", "resolved", "sp50"],
        "escalation_reason": None,
        "customer_sentiment": "Positive",
        "csat_score": 5,
        "product": "sp50",
        "processed_at": (datetime.now() - timedelta(hours=8)).isoformat(),
        "transcript": [
            {"role": "agent", "content": "Hello, I'm GARD. How can I help you?", "timestamp": (datetime.now() - timedelta(hours=8, minutes=3, seconds=30)).isoformat()},
            {"role": "user", "content": "I need to replace the roller brush on my SP50.", "timestamp": (datetime.now() - timedelta(hours=8, minutes=3, seconds=15)).isoformat()},
            {"role": "agent", "content": "Sure! First, power off the machine and open the left door by releasing the latch. You'll see the roller brush at the bottom.", "timestamp": (datetime.now() - timedelta(hours=8, minutes=2, seconds=50)).isoformat()},
            {"role": "user", "content": "OK, I see it. How do I remove it?", "timestamp": (datetime.now() - timedelta(hours=8, minutes=2, seconds=20)).isoformat()},
            {"role": "agent", "content": "Ensure the brush is in the raised position, then loosen the knob on the right side and slide the brush out to the left. The new brush slides in the same way — knob on the right.", "timestamp": (datetime.now() - timedelta(hours=8, minutes=1, seconds=40)).isoformat()},
            {"role": "user", "content": "Done! That was easy. Thanks!", "timestamp": (datetime.now() - timedelta(hours=8, minutes=0, seconds=30)).isoformat()},
        ],
    },
    {
        "call_id": "K5-2201",
        "session_id": "K5-2201",
        "duration_seconds": 178,
        "outcome": "resolved",
        "primary_topic": "product_specs",
        "secondary_topics": ["pricing_sales"],
        "agents_activated": ["product_knowledge"],
        "issue_resolved": True,
        "robot_model": "K5",
        "sentiment": {"start": "neutral", "end": "positive", "shift": "stable_positive"},
        "predicted_csat": 4,
        "actual_csat": 4,
        "follow_up_needed": False,
        "follow_up_action": None,
        "summary": "Security manager asked about K5 patrol coverage and sensor specs. AI provided full specs and caller was satisfied. Also expressed interest in adding more units.",
        "tags": ["specs", "patrol", "sensors", "resolved", "k5", "upgrade"],
        "escalation_reason": None,
        "customer_sentiment": "Positive",
        "csat_score": 4,
        "product": "k5",
        "processed_at": (datetime.now() - timedelta(hours=10)).isoformat(),
        "transcript": [
            {"role": "agent", "content": "Hello, I'm GARD. How can I help you?", "timestamp": (datetime.now() - timedelta(hours=10, minutes=3)).isoformat()},
            {"role": "user", "content": "What's the patrol range of the Knightscope K5?", "timestamp": (datetime.now() - timedelta(hours=10, minutes=2, seconds=45)).isoformat()},
            {"role": "agent", "content": "The K5 has a patrol range of up to 3 miles on a single charge, with 360-degree LiDAR and 4 HD cameras for full perimeter coverage.", "timestamp": (datetime.now() - timedelta(hours=10, minutes=2, seconds=15)).isoformat()},
            {"role": "user", "content": "That's great. We might want to add two more units to our campus.", "timestamp": (datetime.now() - timedelta(hours=10, minutes=1, seconds=30)).isoformat()},
            {"role": "agent", "content": "Excellent! I can have our sales team reach out with a multi-unit fleet discount package. Would you like that?", "timestamp": (datetime.now() - timedelta(hours=10, minutes=1)).isoformat()},
        ],
    },
    {
        "call_id": "YARBO-0701",
        "session_id": "YARBO-0701",
        "duration_seconds": 120,
        "outcome": "resolved",
        "primary_topic": "general_maintenance",
        "secondary_topics": [],
        "agents_activated": ["maintenance"],
        "issue_resolved": True,
        "robot_model": "Yarbo",
        "sentiment": {"start": "neutral", "end": "positive", "shift": "stable_positive"},
        "predicted_csat": 4,
        "actual_csat": None,
        "follow_up_needed": False,
        "follow_up_action": None,
        "summary": "Caller asked about winterizing their Yarbo outdoor robot. AI provided seasonal storage guidelines.",
        "tags": ["seasonal", "storage", "maintenance", "resolved", "yarbo"],
        "escalation_reason": None,
        "customer_sentiment": "Positive",
        "csat_score": 4,
        "product": "yarbo",
        "processed_at": (datetime.now() - timedelta(hours=12)).isoformat(),
        "transcript": [
            {"role": "agent", "content": "Hello, I'm GARD. How can I help?", "timestamp": (datetime.now() - timedelta(hours=12, minutes=2)).isoformat()},
            {"role": "user", "content": "How should I store my Yarbo for the winter?", "timestamp": (datetime.now() - timedelta(hours=12, minutes=1, seconds=45)).isoformat()},
            {"role": "agent", "content": "For winter storage, charge the battery to 60%, store indoors above 40F, and cover the unit. Run it briefly every 30 days to keep the battery healthy.", "timestamp": (datetime.now() - timedelta(hours=12, minutes=1)).isoformat()},
        ],
    },
]

# ─────────────────────────────────────────────
# 2. DASHBOARD_METRICS (pre-aggregated daily)
# ─────────────────────────────────────────────
DASHBOARD_METRICS = []
for i in range(7):
    day = (datetime.now() - timedelta(days=6-i)).strftime("%Y-%m-%d")
    base_calls = 12 + (i * 3)
    DASHBOARD_METRICS.append({
        "date": day,
        "total_calls": base_calls,
        "resolved_calls": int(base_calls * 0.75),
        "escalated_calls": int(base_calls * 0.10),
        "partial_calls": int(base_calls * 0.10),
        "abandoned_calls": int(base_calls * 0.05),
        "fcr_rate": round(75 + (i * 1.5), 1),
        "containment_rate": round(88 + (i * 0.8), 1),
        "avg_csat": round(4.0 + (i * 0.1), 1),
        "topic_counts": {
            "robot_fails_to_charge": 3 + i,
            "roller_brush_maintenance": 2 + (i % 3),
            "operation_how_to": 2 + (i % 2),
            "product_specs": 1 + (i % 2),
            "robot_stuttering": 1,
            "general_inquiry": 1 + (i % 3),
        },
        "sentiment_shifts": {
            "negative_to_positive": 4 + i,
            "stable_positive": 3 + i,
            "stable_neutral": 2,
            "degraded": 1,
        },
        "agent_counts": {
            "troubleshooting": 5 + i,
            "maintenance": 3 + (i % 2),
            "product_knowledge": 2 + (i % 3),
        },
        "updated_at": datetime.now().isoformat(),
    })

# ─────────────────────────────────────────────
# 3. ESCALATION_TICKETS
# ─────────────────────────────────────────────
ESCALATION_TICKETS = [
    {"ticket_id": "ESC-001", "call_id": "V3-1099", "reason": "Hardware failure — screen unresponsive", "product": "v3", "status": "open", "priority": "critical", "created_at": (datetime.now() - timedelta(hours=6)).isoformat(), "summary": "temi V3 screen frozen. Multiple reset attempts failed. Requires on-site technician.", "tags": ["screen", "frozen", "v3"]},
    {"ticket_id": "ESC-002", "call_id": "SP50-9910", "reason": "Complex motor assembly failure", "product": "sp50", "status": "open", "priority": "high", "created_at": (datetime.now() - timedelta(hours=18)).isoformat(), "summary": "SP50 making grinding noise from wheel hub. Internal motor may need replacement.", "tags": ["motor", "noise", "sp50"]},
    {"ticket_id": "ESC-003", "call_id": "W3-5521", "reason": "Billing dispute", "product": "w3", "status": "in_progress", "priority": "medium", "created_at": (datetime.now() - timedelta(days=1)).isoformat(), "summary": "Customer disputes extended warranty charge on Keenon W3 delivery unit.", "tags": ["billing", "warranty", "w3"]},
    {"ticket_id": "ESC-004", "call_id": "K5-3301", "reason": "Safety incident", "product": "k5", "status": "open", "priority": "critical", "created_at": (datetime.now() - timedelta(days=1, hours=5)).isoformat(), "summary": "K5 patrol robot collided with a visitor in parking garage. No injury. Requires sensor recalibration.", "tags": ["collision", "safety", "k5"]},
    {"ticket_id": "ESC-005", "call_id": "SP50-7782", "reason": "Irate customer — repeated failures", "product": "sp50", "status": "resolved", "priority": "high", "created_at": (datetime.now() - timedelta(days=2)).isoformat(), "summary": "Customer experienced 3 cleaning failures in one week. Demanding unit replacement. Resolved with firmware update.", "tags": ["repeated_failure", "irate", "sp50"]},
    {"ticket_id": "ESC-006", "call_id": "YARBO-0802", "reason": "Software malfunction", "product": "yarbo", "status": "open", "priority": "medium", "created_at": (datetime.now() - timedelta(days=2, hours=8)).isoformat(), "summary": "Yarbo mowing pattern keeps drifting outside boundary wire. GPS calibration may be off.", "tags": ["gps", "boundary", "yarbo"]},
]

# ─────────────────────────────────────────────
# 4. SALES_LEADS
# ─────────────────────────────────────────────
SALES_LEADS = [
    {"lead_id": "LEAD-001", "call_id": "K5-2201", "product": "k5", "opportunity": "Multi-unit Fleet Discount Package", "estimated_revenue": 2500, "confidence": "high", "detected_at": (datetime.now() - timedelta(hours=10)).isoformat(), "source": "post_call_analysis"},
    {"lead_id": "LEAD-002", "call_id": "SP50-8801", "product": "sp50", "opportunity": "High-Capacity Battery Upgrade", "estimated_revenue": 125, "confidence": "high", "detected_at": (datetime.now() - timedelta(hours=2)).isoformat(), "source": "post_call_analysis"},
    {"lead_id": "LEAD-003", "call_id": "W3-3392", "product": "w3", "opportunity": "Premium Mapping Software Tier", "estimated_revenue": 499, "confidence": "medium", "detected_at": (datetime.now() - timedelta(hours=4)).isoformat(), "source": "post_call_analysis"},
    {"lead_id": "LEAD-004", "call_id": "SP50-4421", "product": "sp50", "opportunity": "Extended Maintenance Warranty", "estimated_revenue": 300, "confidence": "high", "detected_at": (datetime.now() - timedelta(hours=8)).isoformat(), "source": "post_call_analysis"},
    {"lead_id": "LEAD-005", "call_id": "V3-1099", "product": "v3", "opportunity": "On-site Technician Dispatch", "estimated_revenue": 300, "confidence": "low", "detected_at": (datetime.now() - timedelta(hours=6)).isoformat(), "source": "post_call_analysis"},
    {"lead_id": "LEAD-006", "call_id": "YARBO-0701", "product": "yarbo", "opportunity": "Snow Blower Attachment Add-on", "estimated_revenue": 450, "confidence": "medium", "detected_at": (datetime.now() - timedelta(hours=12)).isoformat(), "source": "post_call_analysis"},
]

# ─────────────────────────────────────────────
# 5. FLEET_ROBOTS
# ─────────────────────────────────────────────
FLEET_ROBOTS = [
    # SP50 Cleaning Robots
    {"robot_id": "SP50-001", "model": "CenoBots SP50", "product": "sp50", "status": "online", "battery_level": 82, "assigned_task": "Deep Cleaning", "area": "Main Lobby East", "last_ping": (datetime.now() - timedelta(minutes=2)).isoformat(), "last_error": None, "firmware": "v3.2.1", "total_hours": 1420, "last_maintenance_date": (datetime.now() - timedelta(days=14)).isoformat()},
    {"robot_id": "SP50-002", "model": "CenoBots SP50", "product": "sp50", "status": "online", "battery_level": 67, "assigned_task": "Scheduled Task", "area": "Hallway B-South", "last_ping": (datetime.now() - timedelta(minutes=1)).isoformat(), "last_error": None, "firmware": "v3.2.1", "total_hours": 980, "last_maintenance_date": (datetime.now() - timedelta(days=7)).isoformat()},
    {"robot_id": "SP50-003", "model": "CenoBots SP50", "product": "sp50", "status": "charging", "battery_level": 23, "assigned_task": "Charging", "area": "Dock Station A", "last_ping": (datetime.now() - timedelta(minutes=1)).isoformat(), "last_error": None, "firmware": "v3.2.1", "total_hours": 2100, "last_maintenance_date": (datetime.now() - timedelta(days=30)).isoformat()},
    {"robot_id": "SP50-004", "model": "CenoBots SP50", "product": "sp50", "status": "error", "battery_level": 45, "assigned_task": "Idle", "area": "Casino Floor A", "last_ping": (datetime.now() - timedelta(minutes=15)).isoformat(), "last_error": "E-STOP_ACTIVE", "firmware": "v3.2.0", "total_hours": 3200, "last_maintenance_date": (datetime.now() - timedelta(days=45)).isoformat()},
    {"robot_id": "SP50-005", "model": "CenoBots SP50", "product": "sp50", "status": "online", "battery_level": 91, "assigned_task": "Mapping", "area": "Conference Room 3", "last_ping": (datetime.now() - timedelta(seconds=30)).isoformat(), "last_error": None, "firmware": "v3.2.1", "total_hours": 560, "last_maintenance_date": (datetime.now() - timedelta(days=3)).isoformat()},
    # Keenon W3 Delivery Robots
    {"robot_id": "W3-001", "model": "Keenon W3", "product": "w3", "status": "online", "battery_level": 76, "assigned_task": "Delivery Run", "area": "Restaurant Floor 2", "last_ping": (datetime.now() - timedelta(minutes=1)).isoformat(), "last_error": None, "firmware": "v2.8.4", "total_hours": 890, "last_maintenance_date": (datetime.now() - timedelta(days=10)).isoformat()},
    {"robot_id": "W3-002", "model": "Keenon W3", "product": "w3", "status": "online", "battery_level": 55, "assigned_task": "Delivery Run", "area": "Hotel Lobby", "last_ping": (datetime.now() - timedelta(minutes=2)).isoformat(), "last_error": None, "firmware": "v2.8.4", "total_hours": 1200, "last_maintenance_date": (datetime.now() - timedelta(days=21)).isoformat()},
    {"robot_id": "W3-003", "model": "Keenon W3", "product": "w3", "status": "offline", "battery_level": 0, "assigned_task": "Offline", "area": "Storage Room B", "last_ping": (datetime.now() - timedelta(hours=3)).isoformat(), "last_error": "BATTERY_DEAD", "firmware": "v2.8.3", "total_hours": 2400, "last_maintenance_date": (datetime.now() - timedelta(days=60)).isoformat()},
    # temi V3 Interactive
    {"robot_id": "V3-001", "model": "temi V3", "product": "v3", "status": "online", "battery_level": 88, "assigned_task": "Wayfinding", "area": "Hospital Reception", "last_ping": (datetime.now() - timedelta(seconds=45)).isoformat(), "last_error": None, "firmware": "v4.1.0", "total_hours": 650, "last_maintenance_date": (datetime.now() - timedelta(days=5)).isoformat()},
    {"robot_id": "V3-002", "model": "temi V3", "product": "v3", "status": "error", "battery_level": 34, "assigned_task": "Idle", "area": "Senior Living Lobby", "last_ping": (datetime.now() - timedelta(minutes=20)).isoformat(), "last_error": "SCREEN_FROZEN", "firmware": "v4.0.9", "total_hours": 1800, "last_maintenance_date": (datetime.now() - timedelta(days=35)).isoformat()},
    # Knightscope K5 Security
    {"robot_id": "K5-001", "model": "Knightscope K5", "product": "k5", "status": "online", "battery_level": 95, "assigned_task": "Patrol Mode", "area": "Parking Garage B", "last_ping": (datetime.now() - timedelta(seconds=15)).isoformat(), "last_error": None, "firmware": "v5.3.2", "total_hours": 4500, "last_maintenance_date": (datetime.now() - timedelta(days=7)).isoformat()},
    {"robot_id": "K5-002", "model": "Knightscope K5", "product": "k5", "status": "online", "battery_level": 71, "assigned_task": "Patrol Mode", "area": "Campus Perimeter North", "last_ping": (datetime.now() - timedelta(minutes=1)).isoformat(), "last_error": None, "firmware": "v5.3.2", "total_hours": 3800, "last_maintenance_date": (datetime.now() - timedelta(days=12)).isoformat()},
    # Yarbo Outdoor
    {"robot_id": "YARBO-001", "model": "Yarbo S1", "product": "yarbo", "status": "online", "battery_level": 60, "assigned_task": "Mowing", "area": "Campus Lawn East", "last_ping": (datetime.now() - timedelta(minutes=3)).isoformat(), "last_error": None, "firmware": "v1.4.0", "total_hours": 320, "last_maintenance_date": (datetime.now() - timedelta(days=8)).isoformat()},
    {"robot_id": "YARBO-002", "model": "Yarbo S1", "product": "yarbo", "status": "charging", "battery_level": 15, "assigned_task": "Charging", "area": "Maintenance Shed", "last_ping": (datetime.now() - timedelta(minutes=5)).isoformat(), "last_error": None, "firmware": "v1.4.0", "total_hours": 280, "last_maintenance_date": (datetime.now() - timedelta(days=15)).isoformat()},
]

# ─────────────────────────────────────────────
# 6. SCHEDULED_MAINTENANCE
# ─────────────────────────────────────────────
SCHEDULED_MAINTENANCE = [
    {"appointment_id": "MAINT-001", "type": "service", "robot_id": "SP50-004", "product": "sp50", "scheduled_date": (datetime.now() + timedelta(days=2)).isoformat(), "status": "scheduled", "description": "E-stop mechanism inspection and reset", "technician": "Mike Rivera"},
    {"appointment_id": "MAINT-002", "type": "service", "robot_id": "V3-002", "product": "v3", "scheduled_date": (datetime.now() + timedelta(days=1)).isoformat(), "status": "scheduled", "description": "Screen replacement and firmware update", "technician": "Lisa Chen"},
    {"appointment_id": "MAINT-003", "type": "service", "robot_id": "W3-003", "product": "w3", "scheduled_date": (datetime.now() + timedelta(days=3)).isoformat(), "status": "scheduled", "description": "Battery replacement — unit completely dead", "technician": "James Okoro"},
    {"appointment_id": "MAINT-004", "type": "demo", "robot_id": None, "product": "k5", "scheduled_date": (datetime.now() + timedelta(days=5)).isoformat(), "status": "confirmed", "description": "Live K5 demo for Sunrise Hospital security team", "technician": None},
    {"appointment_id": "MAINT-005", "type": "service", "robot_id": "SP50-003", "product": "sp50", "scheduled_date": (datetime.now() - timedelta(days=1)).isoformat(), "status": "completed", "description": "Quarterly maintenance — sensor cleaning, brush inspection", "technician": "Mike Rivera"},
    {"appointment_id": "MAINT-006", "type": "demo", "robot_id": None, "product": "yarbo", "scheduled_date": (datetime.now() + timedelta(days=7)).isoformat(), "status": "scheduled", "description": "Yarbo outdoor demo for Greenfield Estates HOA", "technician": None},
]

# ─────────────────────────────────────────────
# 7. SECURITY_EVENTS
# ─────────────────────────────────────────────
SECURITY_EVENTS = [
    {"event_id": "SEC-001", "event_type": "auth_success", "severity": "info", "user": "sarah.jenkins", "status": "success", "timestamp": (datetime.now() - timedelta(hours=1)).isoformat(), "details": "Dashboard login from 192.168.1.45"},
    {"event_id": "SEC-002", "event_type": "auth_failure", "severity": "warning", "user": "unknown", "status": "blocked", "timestamp": (datetime.now() - timedelta(hours=3)).isoformat(), "details": "3 failed login attempts from 45.33.22.11"},
    {"event_id": "SEC-003", "event_type": "pii_redaction", "severity": "info", "user": "system", "status": "success", "timestamp": (datetime.now() - timedelta(hours=2)).isoformat(), "details": "Redacted 12 PII tokens from call SP50-8801 transcript"},
    {"event_id": "SEC-004", "event_type": "vulnerability_scan", "severity": "info", "user": "skadi_frostbow", "status": "clean", "timestamp": (datetime.now() - timedelta(hours=6)).isoformat(), "details": "Weekly fleet vulnerability scan — 0 issues found across 15 robots"},
    {"event_id": "SEC-005", "event_type": "api_key_rotate", "severity": "info", "user": "admin", "status": "success", "timestamp": (datetime.now() - timedelta(days=1)).isoformat(), "details": "Lyzr API key rotated per 30-day policy"},
    {"event_id": "SEC-006", "event_type": "threat_detected", "severity": "critical", "user": "K5-001", "status": "mitigated", "timestamp": (datetime.now() - timedelta(hours=18)).isoformat(), "details": "K5-001 detected unauthorized person in restricted area. Alert sent to security."},
]


async def seed():
    print(f"Connecting to MongoDB: {DATABASE_NAME}...")
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[DATABASE_NAME]

    collections = {
        "calls": CALLS,
        "dashboard_metrics": DASHBOARD_METRICS,
        "escalation_tickets": ESCALATION_TICKETS,
        "sales_leads": SALES_LEADS,
        "fleet_robots": FLEET_ROBOTS,
        "scheduled_maintenance": SCHEDULED_MAINTENANCE,
        "security_events": SECURITY_EVENTS,
    }

    for name, docs in collections.items():
        # Drop existing data
        await db[name].delete_many({})
        if docs:
            await db[name].insert_many(docs)
        print(f"  {name}: {len(docs)} documents seeded")

    print(f"\nAll 7 collections seeded into '{DATABASE_NAME}'.")
    print("Note: 'transcripts' collection is NOT seeded — it's populated by live calls.")
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
