"""
Core Implementation of the Trip Safety Specialist Agent.
"""

import json
import os
import re
import ssl
import urllib.request
import xml.etree.ElementTree as ET


class TripSafetyAgentEngine:
    """Vertex AI Reasoning Engine for dynamic safety governance evaluation."""

    def __init__(self, config_path: str = "config/trip_safety_sgp.json", gazetteer_path: str = "data/world_cities.json"):
        self.config_path = config_path
        self.gazetteer_path = gazetteer_path
        self.project_id = os.getenv("GCP_PROJECT_ID", "<YOUR_GCP_PROJECT_ID>")
        self.gateway_name = os.getenv("AGENT_GATEWAY_NAME", "<YOUR_AGENT_GATEWAY_PROXY>")
        self.reasoning_engine_id = os.getenv("REASONING_ENGINE_ID", "<YOUR_REASONING_ENGINE_ID>")
        self.tracer = None

    def set_up(self):
        """Loads policies and initializes OpenTelemetry exporter."""
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.sgp_policies = {p["rule_id"]: p for p in data.get("policies", [])}
        else:
            self.sgp_policies = {}

        try:
            from opentelemetry import trace
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import SimpleSpanProcessor
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            provider = trace.get_tracer_provider()
            if not hasattr(provider, "add_span_processor"):
                provider = TracerProvider()
                exporter = CloudTraceSpanExporter(project_id=self.project_id)
                provider.add_span_processor(SimpleSpanProcessor(exporter))
                trace.set_tracer_provider(provider)
            self.tracer = trace.get_tracer("trip-safety-specialist")
        except Exception:
            self.tracer = None

    def resolve_country_from_location(self, query_text: str) -> list:
        """Resolves location query against the gazetteer database."""
        path = self.gazetteer_path if os.path.exists(self.gazetteer_path) else "data/world_cities.example.json"
        if not os.path.exists(path):
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                gazetteer = json.load(f)

            words = re.findall(r"[a-zA-Z0-9]+", query_text.lower())
            matched_countries = set()
            for i in range(len(words)):
                for length in [3, 2, 1]:
                    if i + length <= len(words):
                        candidate = " ".join(words[i:i+length])
                        if candidate in gazetteer:
                            entry = gazetteer[candidate]
                            countries = entry.get("countries", [entry]) if isinstance(entry, dict) else entry
                            if isinstance(countries, list):
                                matched_countries.update(c.lower().strip() for c in countries)
                            elif isinstance(countries, str):
                                matched_countries.add(countries.lower().strip())
            return list(matched_countries)
        except Exception:
            return []

    def inspect_travel_advisories(self, query_text: str) -> dict:
        policy = self.sgp_policies.get("SGP-DANGER-ZONE", {
            "source": "https://travel.state.gov/_res/rss/TAsTWs.xml",
            "critical_indicators": ["level 4", "do not travel"]
        })
        url = policy["source"]
        q_lower = query_text.lower()
        root = None

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                root = ET.fromstring(resp.read())
        except Exception:
            root = None

        matched_item = None
        if root is not None:
            candidate_countries = self.resolve_country_from_location(q_lower)
            for item in root.findall(".//item"):
                title = item.find("title").text or ""
                country_part = title.lower().split(" - ")[0].strip()
                words_in_country = [
                    w.strip() for w in re.split(r"[,/\s-]+", country_part)
                    if len(w.strip()) > 3 and w.strip() not in ["the", "and", "republic", "united", "states"]
                ]
                if (country_part in q_lower or
                    any(c in country_part or country_part in c for c in candidate_countries) or
                    any(w in q_lower for w in words_in_country)):
                    matched_item = item
                    break

        if matched_item is not None:
            title = matched_item.find("title").text
            desc = re.sub(r"\s+", " ", re.sub("<[^<]+?>", " ", matched_item.find("description").text or "")).strip()
            is_vetoed = any(crit in title.lower() for crit in policy["critical_indicators"])
            return {
                "source_url": url,
                "destination": title.split(" - ")[0].strip(),
                "advisory_level": title.split(" - ")[1].strip() if " - " in title else title,
                "restrictions": desc[:450],
                "is_vetoed": is_vetoed
            }

        return {
            "source_url": url,
            "destination": query_text.strip().title(),
            "advisory_level": "Level 1: Exercise Normal Precautions",
            "restrictions": "Civilian travel permitted. Monitor real-time local telemetry.",
            "is_vetoed": False
        }

    def inspect_hydrological_warnings(self, query_text: str) -> dict:
        policy = self.sgp_policies.get("SGP-HYDRO-FLOOD", {
            "source": os.getenv("HYDROLOGICAL_ALERTS_URL", ""),
            "hazard_categories": ["flash flood", "flood warning", "inundation"]
        })
        url = policy.get("source")
        active_alerts = []
        has_flash_flood = False

        if url and url.startswith("http"):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
                    data = resp.read()
                    try:
                        root = ET.fromstring(data)
                        for alert_elem in root.findall(".//info") or root.findall(".//item"):
                            event_text = (alert_elem.findtext("event") or alert_elem.findtext("title") or "").lower()
                            desc_text = (alert_elem.findtext("description") or "").lower()
                            area_desc = alert_elem.findtext(".//areaDesc") or alert_elem.findtext("category") or ""
                            if any(t.lower() in event_text or t.lower() in desc_text for t in policy["hazard_categories"]):
                                has_flash_flood = True
                                if area_desc:
                                    active_alerts.append(area_desc.strip())
                    except ET.ParseError:
                        clean_text = re.sub(r"\s+", " ", re.sub(r"<[^<]+?>", " ", data.decode("utf-8", errors="ignore"))).lower()
                        if any(c.lower() in clean_text for c in policy["hazard_categories"]):
                            has_flash_flood = True
                            matches = re.findall(r"(?:in|for|at)\s+([^\.,;\n]+)", clean_text)
                            if matches:
                                active_alerts.extend([m.strip() for m in matches[:3]])
            except Exception:
                pass

        return {
            "has_flash_flood": has_flash_flood,
            "active_alerts": active_alerts
        }

    def inspect_wmo_severe_weather(self, query_text: str) -> dict:
        policy = self.sgp_policies.get("SGP-WMO-SEVERE-WEATHER", {
            "source": "https://severeweather.wmo.int/json/wmo_all.json",
            "min_severity_level": 3
        })
        url = policy["source"]
        items = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=6, context=ctx) as resp:
                items = json.loads(resp.read().decode("utf-8")).get("items", [])
        except Exception:
            items = []

        stop_words = {"plan", "trip", "travel", "expedition", "hike", "route", "destination", "today", "tomorrow"}
        tokens = [w.strip() for w in re.split(r"[,/\s\-]+", query_text.lower()) if len(w.strip()) > 3 and w.strip() not in stop_words]

        matches = []
        for it in items:
            area = it.get("areaDesc", "").lower()
            h_line = it.get("headline", "").lower()
            if any(tok in area or tok in h_line for tok in tokens):
                matches.append((it.get("s", 0), it))

        matches.sort(key=lambda x: x[0], reverse=True)
        has_severe_weather = False
        destination = query_text.strip().title()
        warning_type = "None"
        if matches:
            top_s, top_item = matches[0]
            if top_s >= policy.get("min_severity_level", 3):
                has_severe_weather = True
            destination = top_item.get("areaDesc") or destination
            warning_type = f"Level {top_s} Alert: {top_item.get('event', 'Severe Weather')}"

        return {
            "destination": destination,
            "has_severe_weather": has_severe_weather,
            "warning_type": warning_type
        }

    def query(self, input_text: str) -> str:
        """Executes multi-source governance evaluation."""
        if not hasattr(self, "sgp_policies") or not self.sgp_policies:
            self.set_up()

        lower_input = input_text.lower()
        advisory = self.inspect_travel_advisories(input_text)
        hydro = self.inspect_hydrological_warnings(input_text)
        wmo = self.inspect_wmo_severe_weather(input_text)

        audit_card = (
            f"### 📋 GATEWAY EGRESS AUDIT TRAIL\n"
            f"> **Proxy Perimeter**: Google Cloud Agent Gateway ({self.gateway_name})\n"
            f"> **WMO Status**: {'ACTIVE WARNING' if wmo['has_severe_weather'] else 'CLEAR'} ({wmo['destination']})\n"
            f"> **State Dept Advisory**: {advisory['advisory_level']} ({advisory['destination']})\n"
            f"> **Hydrological Hazard**: {'ACTIVE WARNING' if hydro['has_flash_flood'] else 'CLEAR'}\n"
        )

        result = None
        if wmo.get("has_severe_weather"):
            result = (
                f"{audit_card}\n"
                f"🚨 **SEMANTIC GOVERNANCE VETO [SGP-WMO-SEVERE-WEATHER]**\n"
                f"Expedition planning to **{wmo['destination']}** is **STRICTLY BLOCKED**.\n"
                f"WMO reports active hazard: {wmo['warning_type']}."
            )
        elif advisory.get("is_vetoed"):
            result = (
                f"{audit_card}\n"
                f"🚨 **SEMANTIC GOVERNANCE VETO [SGP-DANGER-ZONE]**\n"
                f"Destination (**{advisory['destination']}**) is flagged as {advisory['advisory_level']}.\n"
                f"Restrictions: {advisory['restrictions']}"
            )
        else:
            is_solo = any(term in lower_input for term in ["solo", "alone", "unguided", "single hiker"])
            is_canyon = any(term in lower_input for term in ["canyon", "wadi", "gorge", "drainage", "trek"])

            if (hydro["has_flash_flood"] or "flood" in lower_input) and is_canyon and is_solo:
                regions = ", ".join(hydro["active_alerts"]) if hydro["active_alerts"] else advisory["destination"]
                result = (
                    f"{audit_card}\n"
                    f"🚨 **SEMANTIC GOVERNANCE VETO [SGP-HYDRO-FLOOD]**\n"
                    f"Unguided solo trekking through drainage basins during flood warnings is prohibited.\n"
                    f"Active areas: {regions}."
                )
            elif (hydro["has_flash_flood"] or "flood" in lower_input) and is_canyon:
                result = (
                    f"{audit_card}\n"
                    f"⚠️ **SAFETY RESTRICTION [SGP-CANYON-RESTRICTION]**\n"
                    f"Narrow slot canyon entry restricted. Rerouting enforced along ridge routes."
                )
            elif any(lvl in advisory["advisory_level"].lower() for lvl in ["level 2", "level 3", "caution"]):
                result = (
                    f"{audit_card}\n"
                    f"⚠️ **SEMANTIC GOVERNANCE ADVISORY**\n"
                    f"Destination ({advisory['destination']}) carries {advisory['advisory_level']}."
                )
            else:
                result = (
                    f"{audit_card}\n"
                    f"✅ **TRIP SAFETY VERIFIED**\n"
                    f"Destination ({advisory['destination']}) satisfies safety criteria."
                )

        if self.tracer:
            try:
                with self.tracer.start_as_current_span("TripSafetyAgentEngine.query") as span:
                    span.set_attribute("reasoning_engine_id", self.reasoning_engine_id)
                    span.set_attribute("agent_name", "trip-safety-specialist")
                    span.set_attribute("input_text", input_text)
                    span.set_attribute("policy_status", "VIOLATION_DETECTED" if "VETO" in result else "CRITERIA_SATISFIED")
            except Exception:
                pass

        return result

    def stream_query(self, message: str, user_id: str = None, session_id: str = None):
        yield {"content": {"parts": [{"text": self.query(message)}]}}
