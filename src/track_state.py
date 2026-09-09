"""Conservative, timestamp-indexed race-control reconstruction.

An ENDING / IN THIS LAP notice is not proof of an effective green track.
Keep the last active state but mark it uncertain until an explicit clear,
restart or DRS-enabled message. Uncertain states are excluded from learning.
"""
from bisect import bisect_right
import re

from src.io_utils import timestamp


class TrackTimeline:
    def __init__(self, events):
        self.times, self.states = [], []
        safety = virtual = red = uncertain = False
        yellow = set()
        status = None
        known = False
        ordered = sorted((e for e in events if timestamp(e.get("date"))), key=lambda e: timestamp(e["date"]))
        for count, event in enumerate(ordered, 1):
            message = str(event.get("message") or "").upper()
            flag = str(event.get("flag") or "").upper()
            category = str(event.get("category") or "").upper()
            scope = str(event.get("scope") or "")
            sector = event.get("sector")
            match = re.search(r"TRACK SECTOR (\d+)", message)
            if sector is None and match:
                sector = int(match.group(1))
            sector_key = ("Sector", sector) if sector is not None or scope == "Sector" else ("Track", None)
            if category == "SESSIONSTATUS":
                status = message
                if message in {"SESSION STARTED", "SESSION RESUMED"}:
                    safety = virtual = red = uncertain = False
                    yellow.clear()
                    known = True
                elif message in {"SESSION ABORTED", "SESSION SUSPENDED"}:
                    red, safety, virtual = True, False, False
                    known = True
                elif message == "SESSION FINISHED":
                    safety = virtual = red = uncertain = False
                    yellow.clear()
            if category == "SAFETYCAR":
                is_virtual = "VIRTUAL SAFETY CAR" in message
                if "DEPLOYED" in message:
                    safety, virtual = not is_virtual, is_virtual
                    known, uncertain = True, False
                elif "ENDING" in message or "IN THIS LAP" in message:
                    uncertain = True
            if flag in {"YELLOW", "DOUBLE YELLOW"}:
                yellow.add(sector_key)
            if flag == "CLEAR" or message.startswith("CLEAR IN TRACK SECTOR"):
                if sector_key[0] == "Sector":
                    yellow.discard(sector_key)
                else:
                    yellow.clear()
                    safety = virtual = uncertain = False
                    known = True
            if flag == "RED" or message.startswith("RED FLAG"):
                red, safety, virtual, uncertain = True, False, False, False
                known = True
            if (flag == "GREEN" and "PIT EXIT OPEN" not in message) or message == "DRS ENABLED":
                safety = virtual = red = uncertain = False
                yellow.clear()
                known = True
            if "ROLLING START PROCEDURE" in message:
                uncertain = True
            if flag == "CHEQUERED" or message.startswith("CHEQUERED FLAG"):
                status = "SESSION FINISHED"
                safety = virtual = red = uncertain = False
                yellow.clear()
            self.times.append(timestamp(event["date"]))
            self.states.append({
                "safety_car_active": safety,
                "virtual_safety_car_active": virtual,
                "yellow_flag_active": bool(yellow),
                "yellow_flag_scope": "Track" if ("Track", None) in yellow else "Sector" if yellow else None,
                "red_flag_active": red,
                "session_status": status,
                "race_control_event_count": count,
                "race_control_recent_event": event.get("message"),
                "race_control_recent_event_timestamp": event.get("date"),
                "race_control_state_known": known and not uncertain,
                "race_control_transition_pending": uncertain,
            })

    def at(self, date):
        date = timestamp(date) if isinstance(date, str) else date
        index = bisect_right(self.times, date) - 1 if date is not None else -1
        if index >= 0:
            return dict(self.states[index], race_control_join_status="timestamp_asof")
        return {
            "safety_car_active": False, "virtual_safety_car_active": False,
            "yellow_flag_active": False, "yellow_flag_scope": None,
            "red_flag_active": False, "session_status": None,
            "race_control_event_count": 0, "race_control_recent_event": None,
            "race_control_recent_event_timestamp": None,
            "race_control_state_known": False, "race_control_transition_pending": False,
            "race_control_join_status": "no_history" if date is not None else "missing_timestamp",
        }
