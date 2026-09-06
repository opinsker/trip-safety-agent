"""Deployment script for Vertex AI Reasoning Engine."""
import os
from dotenv import load_dotenv
import vertexai
from vertexai.preview import reasoning_engines
from src.agent import TripSafetyAgentEngine

load_dotenv()

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "<YOUR_GCP_PROJECT_ID>")
LOCATION = os.getenv("GCP_REGION", "us-central1")
STAGING_BUCKET = os.getenv("GCS_STAGING_BUCKET", "gs://<YOUR_GCS_STAGING_BUCKET>")
REASONING_ENGINE_ID = os.getenv("REASONING_ENGINE_ID")

if __name__ == "__main__":
    vertexai.init(project=PROJECT_ID, location=LOCATION, staging_bucket=STAGING_BUCKET)

    if REASONING_ENGINE_ID:
        print(f"Updating existing Reasoning Engine: {REASONING_ENGINE_ID}...")
        engine = reasoning_engines.ReasoningEngine(REASONING_ENGINE_ID)
        engine.update(
            reasoning_engine=TripSafetyAgentEngine(),
            display_name="trip-safety-specialist",
            description="Agent enforcing dynamic multi-source SGP policies via Agent Gateway.",
            requirements=["google-cloud-aiplatform", "opentelemetry-sdk", "opentelemetry-exporter-gcp-trace"]
        )
    else:
        print("Creating new Reasoning Engine instance...")
        engine = reasoning_engines.ReasoningEngine.create(
            reasoning_engine=TripSafetyAgentEngine(),
            display_name="trip-safety-specialist",
            description="Agent enforcing dynamic multi-source SGP policies via Agent Gateway.",
            requirements=["google-cloud-aiplatform", "opentelemetry-sdk", "opentelemetry-exporter-gcp-trace"]
        )

    print(f"✅ Successfully deployed: {engine.resource_name}")
