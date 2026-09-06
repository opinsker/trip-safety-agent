# Trip Safety Specialist Agent

A Vertex AI Agent Engine and Reasoning Engine designed for autonomous trip safety governance. It evaluates live multi-source telemetry against declarative **Semantic Governance Policies (SGP)** to enforce circuit-breaker decisions (VETO, REROUTE, ADVISORY).

## Features
- **Dynamic Policy Ingestion**: Loads declarative safety policies via `config/trip_safety_sgp.json`.
- **Zero Hardcoded Entities**: Uses external gazetteer datasets (`data/world_cities.json`) for geographic correlation.
- **Multi-Source Telemetry**:
  - Live U.S. State Department Travel Advisories (RSS/XML).
  - Common Alerting Protocol (CAP) & Regional Hydrological Warnings.
  - World Meteorological Organization (WMO SWIC 3.0) Severe Weather Alerts.
- **Enterprise Observability**: Native OpenTelemetry integration with Google Cloud Trace.

## Quickstart

```bash
# 1. Clone repository
git clone https://github.com/<YOUR_USERNAME>/trip-safety-agent.git
cd trip-safety-agent

# 2. Setup virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your GCP project details

# 4. Run tests
pytest tests/
```

## Deployment to Vertex AI

```bash
python deploy.py
```
