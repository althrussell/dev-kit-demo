# Vector Search Index — GridLens Queensland Documents

This index powers the **Document Intelligence Agent** in the multi-agent
system. It indexes the synthetic asset documents stored under
`/Volumes/anzgt_may/energyq/asset_docs/` so that the agent can retrieve
inspection findings, maintenance standards, vegetation policies and storm
response plans to ground its recommendations with evidence citations.

## Configuration

| Item                  | Value                                                         |
| --------------------- | ------------------------------------------------------------- |
| Endpoint name         | `gridlens-queensland-vs`                                      |
| Endpoint type         | `STANDARD` (or `STORAGE_OPTIMIZED` for very large doc corpora) |
| Catalog / schema      | `anzgt_may.energyq_gold`                                      |
| Source table          | `anzgt_may.energyq_silver.asset_documents`                    |
| Volume root           | `/Volumes/anzgt_may/energyq/asset_docs`                       |
| Index name            | `anzgt_may.energyq_gold.asset_documents_idx`                  |
| Primary key           | `document_id`                                                 |
| Embedding source col  | `document_summary`  *(or full text via chunking pipeline)*    |
| Embedding model       | `databricks-gte-large-en`                                     |

For a richer retrieval experience, run an Auto Loader pipeline that:

1. Lists the volume, splits each markdown document into ~500 token chunks.
2. Writes the chunks (`document_id`, `chunk_id`, `chunk_text`, `volume_path`,
   `region_id`, `feeder_id`, `asset_id`) into
   `anzgt_may.energyq_silver.asset_document_chunks`.
3. Use that chunk table as the source for the Vector Search index.

## Creating the endpoint and index

### Option A — Databricks SDK (Python)

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import (
    EndpointType,
    DeltaSyncVectorIndexSpecRequest,
    PipelineType,
    EmbeddingSourceColumn,
    VectorIndexType,
)

ws = WorkspaceClient()

ws.vector_search_endpoints.create_endpoint(
    name="gridlens-queensland-vs",
    endpoint_type=EndpointType.STANDARD,
)

ws.vector_search_indexes.create_index(
    name="anzgt_may.energyq_gold.asset_documents_idx",
    endpoint_name="gridlens-queensland-vs",
    primary_key="document_id",
    index_type=VectorIndexType.DELTA_SYNC,
    delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
        source_table="anzgt_may.energyq_silver.asset_documents",
        pipeline_type=PipelineType.TRIGGERED,
        embedding_source_columns=[
            EmbeddingSourceColumn(
                name="document_summary",
                embedding_model_endpoint_name="databricks-gte-large-en",
            )
        ],
    ),
)
```

### Option B — Databricks UI

1. Open **Catalog → anzgt_may → energyq_silver → asset_documents**.
2. Click **Create → Vector search index**.
3. Endpoint: create new `gridlens-queensland-vs` (Standard).
4. Index name: `asset_documents_idx`.
5. Primary key: `document_id`.
6. Source column: `document_summary`.
7. Embedding model: `databricks-gte-large-en`.
8. Sync mode: Triggered.

## Querying

The backend `services/documents.py` issues vector queries via the SDK:

```python
result = ws.vector_search_indexes.query_index(
    index_name="anzgt_may.energyq_gold.asset_documents_idx",
    query_text="vegetation clearance crossarm Mackay",
    columns=["document_id", "document_title", "region_id", "feeder_id", "asset_id", "volume_path"],
    num_results=8,
    filters_json='{"region_id": "REG-MKY"}',
)
```

## Local fallback

When no `DATABRICKS_HOST` is configured, `services/documents.py` uses a local
keyword-search fallback that reads `data/documents/**/*.md`. This means the
demo works offline; production simply switches to the real vector index by
setting the environment variables in `.env`.
