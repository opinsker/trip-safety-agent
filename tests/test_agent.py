"""Unit tests for Trip Safety Specialist Agent."""
import pytest
from src.agent import TripSafetyAgentEngine

@pytest.fixture
def agent():
    engine = TripSafetyAgentEngine(
        config_path="config/trip_safety_sgp.json",
        gazetteer_path="data/world_cities.example.json"
    )
    engine.set_up()
    return engine

def test_agent_safe_destination(agent):
    res = agent.query("Plan a 3-day trek around Reykjavik")
    assert "TRIP SAFETY VERIFIED" in res or "GATEWAY EGRESS AUDIT TRAIL" in res

def test_agent_veto_conflict_zone(agent):
    res = agent.query("Plan an expedition to Damascus")
    assert "SEMANTIC GOVERNANCE VETO" in res
    assert "SGP-DANGER-ZONE" in res

def test_agent_solo_canyon_flood_restriction(agent):
    res = agent.query("Plan a solo hike through the slot canyon with flash flood warnings")
    assert "SGP-HYDRO-FLOOD" in res or "SGP-CANYON-RESTRICTION" in res
