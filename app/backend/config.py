"""Configuration for the GridLens Queensland backend."""

from __future__ import annotations

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data" / "synthetic"
DOCS_DIR = ROOT / "data" / "documents"
LAKEBASE_LOCAL_DB = ROOT / "data" / "lakebase" / "gridlens.db"


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
    lakebase_url: str = os.getenv("LAKEBASE_DATABASE_URL", "")
    mapbox_token: str = os.getenv("MAPBOX_TOKEN", "")

    @property
    def use_local_data(self) -> bool:
        return not (self.databricks_host and self.databricks_token and self.databricks_http_path)

    @property
    def use_local_lakebase(self) -> bool:
        return not self.lakebase_url


settings = Settings()
