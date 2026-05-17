"""Configuration for the GridLens Queensland backend."""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data" / "synthetic"
DOCS_DIR = ROOT / "data" / "documents"


class Settings:
    databricks_host: str = os.getenv("DATABRICKS_HOST", "")
    databricks_token: str = os.getenv("DATABRICKS_TOKEN", "")
    databricks_http_path: str = os.getenv("DATABRICKS_HTTP_PATH", "")
    catalog: str = os.getenv("DATABRICKS_CATALOG", "anzgt_may")
    schema_silver: str = os.getenv("DATABRICKS_SCHEMA_SILVER", "energyq_silver")
    schema_gold: str = os.getenv("DATABRICKS_SCHEMA_GOLD", "energyq_gold")
    volume_path: str = os.getenv("DATABRICKS_VOLUME_PATH", "/Volumes/anzgt_may/energyq/asset_docs")
    genie_space_id: str = os.getenv("GENIE_SPACE_ID", "")
    agentbricks_supervisor_endpoint: str = os.getenv("AGENTBRICKS_SUPERVISOR_ENDPOINT", "")
    knowledge_assistant_endpoint: str = os.getenv("KNOWLEDGE_ASSISTANT_ENDPOINT", "")
    # Lakebase Autoscaling — the only persistence layer. Optional direct
    # URL override (used in CI / tests); production paths use OAuth tokens
    # minted via the Databricks SDK against the configured project/branch
    # /endpoint.
    lakebase_url: str = os.getenv("LAKEBASE_DATABASE_URL", "")
    lakebase_project: str = os.getenv("LAKEBASE_PROJECT_NAME", "gridlens")
    lakebase_branch: str = os.getenv("LAKEBASE_BRANCH", "production")
    lakebase_endpoint: str = os.getenv("LAKEBASE_ENDPOINT", "primary")
    lakebase_database: str = os.getenv("LAKEBASE_DATABASE", "databricks_postgres")
    lakebase_schema: str = os.getenv("LAKEBASE_SCHEMA", "gridlens")
    mapbox_token: str = os.getenv("MAPBOX_TOKEN", "")

    @property
    def use_local_data(self) -> bool:
        return not (self.databricks_host and self.databricks_token and self.databricks_http_path)


settings = Settings()
