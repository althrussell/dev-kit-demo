"""
Document intelligence service.

Three loading modes, picked at startup in this order:

  1. **Volume** — when the app runs on Databricks Apps (or any environment
     where the Databricks SDK can authenticate AND `DATABRICKS_VOLUME_PATH`
     points at a UC volume), all `*.md` files under the volume are pulled
     via the Files API into memory using a thread pool. This avoids
     shipping ~800 documents inside the app source bundle.

  2. **Local filesystem** — when `data/documents/` exists next to the
     backend, falls back to walking the local tree (used for `npm run dev`
     and unit tests).

  3. **Empty** — if neither source is available we log a warning and serve
     an empty index. The MAS still works; grounded evidence will just be
     limited to Delta-table evidence rather than document excerpts.

Whichever mode is active, the in-memory document shape is identical, so
downstream search and `read_full` callers don't care.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from app.backend.config import DOCS_DIR, settings

logger = logging.getLogger(__name__)


_WORD_RE = re.compile(r"[a-zA-Z]{3,}")

# Tunables — sensible defaults for a 6 vCPU app runtime hitting a UC volume.
_VOLUME_LIST_MAX_WORKERS = 8
_VOLUME_FETCH_MAX_WORKERS = 16


def _use_volume_docs() -> bool:
    """Return True when we should attempt to load documents from the UC volume."""
    flag = os.getenv("USE_VOLUME_DOCS", "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    # Auto-detect: if we look like we're inside Databricks Apps, default ON.
    if os.getenv("DATABRICKS_CLIENT_ID") or os.getenv("DATABRICKS_APP_PORT"):
        return bool(settings.volume_path)
    return False


class DocumentSearchService:
    _instance: "DocumentSearchService | None" = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "DocumentSearchService":
        with cls._lock:
            if cls._instance is None:
                cls._instance = DocumentSearchService()
            return cls._instance

    def __init__(self) -> None:
        self.docs: list[dict] = []
        loaded_from_volume = False
        if _use_volume_docs():
            try:
                self._load_from_volume()
                loaded_from_volume = True
            except Exception as e:  # pragma: no cover — defensive
                print(f"[documents] volume load failed ({e!r}); falling back to local files")
        if not loaded_from_volume:
            self._load_local()

    # ------------------------------------------------------------------
    # Volume loader (Databricks SDK Files API)
    # ------------------------------------------------------------------

    def _load_from_volume(self) -> None:
        from databricks.sdk import WorkspaceClient  # type: ignore

        volume_root = settings.volume_path.rstrip("/")
        ws = WorkspaceClient()
        t0 = time.time()
        md_paths = self._list_md_files_concurrent(ws, volume_root)
        print(f"[documents] discovered {len(md_paths)} markdown files under {volume_root} "
              f"({time.time() - t0:.1f}s)")

        t1 = time.time()
        loaded = 0
        with ThreadPoolExecutor(max_workers=_VOLUME_FETCH_MAX_WORKERS) as pool:
            futures = {pool.submit(self._download_volume_doc, ws, p, volume_root): p for p in md_paths}
            for fut in as_completed(futures):
                doc = fut.result()
                if doc is not None:
                    self.docs.append(doc)
                    loaded += 1
        print(f"[documents] loaded {loaded}/{len(md_paths)} markdown documents from volume "
              f"({time.time() - t1:.1f}s)")

    @staticmethod
    def _list_md_files_concurrent(ws, root: str) -> list[str]:
        """BFS the volume tree using a worker pool to keep p99 low on deep trees."""
        results: list[str] = []
        pending: list[str] = [root]
        # Skip the staging subdir that holds CSVs we load Delta tables from.
        skip_segments = {"_staging"}

        while pending:
            batch, pending = pending, []
            with ThreadPoolExecutor(max_workers=_VOLUME_LIST_MAX_WORKERS) as pool:
                future_map = {pool.submit(lambda d=d: list(ws.files.list_directory_contents(d))): d
                              for d in batch}
                for fut in as_completed(future_map):
                    parent = future_map[fut]
                    try:
                        entries = fut.result()
                    except Exception as e:
                        print(f"[documents] list {parent} failed: {e}")
                        continue
                    for ent in entries:
                        p = ent.path
                        seg = p.rsplit("/", 1)[-1]
                        if ent.is_directory:
                            if seg in skip_segments:
                                continue
                            pending.append(p)
                        elif p.endswith(".md"):
                            results.append(p)
        return results

    def _download_volume_doc(self, ws, path: str, volume_root: str) -> Optional[dict]:
        try:
            resp = ws.files.download(path)
            raw = resp.contents.read()
            content = raw.decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"[documents] download {path} failed: {e}")
            return None
        rel = path[len(volume_root):].lstrip("/")
        parts = rel.split("/")
        return self._build_doc(
            rel_path=rel,
            content=content,
            parts=parts,
        )

    # ------------------------------------------------------------------
    # Local filesystem loader (dev / tests)
    # ------------------------------------------------------------------

    def _load_local(self) -> None:
        if not DOCS_DIR.exists():
            print(f"[documents] DOCS_DIR missing: {DOCS_DIR}  (set USE_VOLUME_DOCS=true to load from {settings.volume_path})")
            return
        for path in DOCS_DIR.rglob("*.md"):
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            rel = path.relative_to(DOCS_DIR)
            doc = self._build_doc(
                rel_path=rel.as_posix(),
                content=content,
                parts=list(rel.parts),
            )
            if doc:
                self.docs.append(doc)
        print(f"[documents] indexed {len(self.docs)} local markdown documents")

    # ------------------------------------------------------------------
    # Shared doc construction
    # ------------------------------------------------------------------

    def _build_doc(self, rel_path: str, content: str, parts: list[str]) -> Optional[dict]:
        region_id = parts[0] if len(parts) > 0 else ""
        doc_type = parts[1] if len(parts) > 1 else ""
        document_id = Path(rel_path).stem
        asset_id = ""
        feeder_id = ""
        m = re.search(r"AST-[A-Z]+-[A-Z]+-\d+", content)
        if m:
            asset_id = m.group(0)
        m2 = re.search(r"FDR-[A-Z]+-\d+", content)
        if m2:
            feeder_id = m2.group(0)
        return {
            "document_id": document_id,
            "document_type": doc_type,
            "region_id": region_id,
            "asset_id": asset_id,
            "feeder_id": feeder_id,
            "title": self._extract_title(content) or document_id,
            "content": content,
            "volume_path": f"{settings.volume_path}/{rel_path}",
        }

    @staticmethod
    def _extract_title(body: str) -> Optional[str]:
        for line in body.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return None

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {m.group(0).lower() for m in _WORD_RE.finditer(text)}

    def search(
        self,
        query: str,
        region_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        feeder_id: Optional[str] = None,
        top_k: int = 6,
    ) -> list[dict]:
        terms = self._tokenize(query)
        results = []
        for d in self.docs:
            if region_id and d["region_id"] != region_id:
                continue
            if asset_id and d["asset_id"] and d["asset_id"] != asset_id:
                # Only enforce when doc has an asset_id.
                continue
            if feeder_id and d["feeder_id"] and d["feeder_id"] != feeder_id:
                continue
            content_lower = d["content"].lower()
            score = 0.0
            for term in terms:
                if term in content_lower:
                    score += 1 + (content_lower.count(term) / 8.0)
            # Strong bonus for exact id match.
            if asset_id and asset_id.lower() in content_lower:
                score += 5.0
            if feeder_id and feeder_id.lower() in content_lower:
                score += 3.5
            if score > 0:
                excerpt = self._extract_excerpt(d["content"], terms)
                results.append({
                    **{k: d[k] for k in ("document_id", "document_type", "region_id", "asset_id", "feeder_id", "title", "volume_path")},
                    "score": round(score, 2),
                    "excerpt": excerpt,
                })
        results.sort(key=lambda r: -r["score"])
        return results[:top_k]

    @staticmethod
    def _extract_excerpt(content: str, terms: set[str]) -> str:
        for line in content.splitlines():
            ll = line.lower()
            if any(t in ll for t in terms) and not line.startswith("#"):
                line = line.strip("- ").strip()
                if len(line) > 30:
                    return line[:280]
        # Fallback: first non-heading sentence.
        for line in content.splitlines():
            if line and not line.startswith("#") and len(line) > 30:
                return line.strip("- ").strip()[:280]
        return ""

    def read_full(self, document_id: str) -> Optional[dict]:
        for d in self.docs:
            if d["document_id"] == document_id:
                return d
        return None

    # ------------------------------------------------------------------
    # Knowledge Assistant semantic search
    # ------------------------------------------------------------------

    def semantic_search(
        self,
        query: str,
        region_id: Optional[str] = None,
        top_k: int = 6,
    ) -> dict:
        """Call the gridlens-asset-docs Knowledge Assistant for a grounded answer.

        The KA returns a synthesised answer + citations. We map each citation
        back to our in-memory `docs` index so the frontend can surface the
        same `document_id`, `region_id`, `asset_id`, `feeder_id` and
        `volume_path` it already knows how to render.

        Falls back to local keyword search when:
          - KA endpoint env var is not set, OR
          - the KA call fails for any reason.
        """
        endpoint = os.getenv("KNOWLEDGE_ASSISTANT_ENDPOINT", "").strip()
        if not endpoint:
            hits = self.search(query, region_id=region_id, top_k=top_k)
            return {
                "answer": "",
                "citations": [],
                "hits": hits,
                "source": "keyword",
            }

        try:
            return self._call_ka(endpoint, query, region_id=region_id, top_k=top_k)
        except Exception as e:
            logger.warning("KA call failed (%s); using keyword fallback for %r", e, query[:80])
            hits = self.search(query, region_id=region_id, top_k=top_k)
            return {
                "answer": "",
                "citations": [],
                "hits": hits,
                "source": "keyword-fallback",
                "error": f"{type(e).__name__}: {e}",
            }

    def _call_ka(self, endpoint: str, query: str, *, region_id: Optional[str], top_k: int) -> dict:
        from databricks.sdk import WorkspaceClient
        import requests

        w = WorkspaceClient()
        host = (w.config.host or "").rstrip("/")
        token = w.config.authenticate().get("Authorization", "").removeprefix("Bearer ").strip()
        if not host or not token:
            raise RuntimeError("Could not resolve Databricks host or token for KA call")

        prompt = query
        if region_id:
            prompt = f"[region={region_id}] {query}"

        body = {"input": [{"role": "user", "content": prompt}]}
        url = f"{host}/serving-endpoints/{endpoint}/invocations"
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        answer, citations = self._parse_ka_response(data)
        # Resolve citations back to local docs (best-effort), de-duping by doc_id.
        resolved: list[dict] = []
        seen_ids: set[str] = set()
        for c in citations:
            doc = self._resolve_citation(c)
            cid = (doc.get("document_id") if doc else c.get("document_id")) or ""
            if cid and cid in seen_ids:
                continue
            if cid:
                seen_ids.add(cid)
            if doc:
                resolved.append({
                    **{k: doc[k] for k in (
                        "document_id", "document_type", "region_id", "asset_id",
                        "feeder_id", "title", "volume_path",
                    )},
                    "excerpt": (c.get("excerpt") or doc.get("content", ""))[:280],
                    "score": c.get("score", 0.9),
                })
            else:
                resolved.append({
                    "document_id": c.get("document_id") or c.get("source_ref", "")[-32:],
                    "document_type": c.get("document_type", ""),
                    "region_id": c.get("region_id", region_id or ""),
                    "asset_id": "",
                    "feeder_id": "",
                    "title": c.get("title") or c.get("source_ref", "KA citation"),
                    "volume_path": c.get("volume_path", c.get("source_ref", "")),
                    "excerpt": (c.get("excerpt") or "")[:280],
                    "score": c.get("score", 0.9),
                })
        return {
            "answer": answer,
            "citations": citations,
            "hits": resolved[:top_k],
            "source": "knowledge-assistant",
        }

    @staticmethod
    def _parse_ka_response(data: dict) -> tuple[str, list[dict]]:
        """Extract the grounded answer + citation list from a Responses-API reply."""
        # Responses-API style: {"output": [{"type":"message","content":[{"type":"output_text","text":"..."}]}], "citations": [...]}
        answer_parts: list[str] = []
        citations: list[dict] = []

        for out in (data.get("output") or []):
            t = out.get("type")
            if t == "message":
                for piece in (out.get("content") or []):
                    if piece.get("type") in ("output_text", "text"):
                        txt = piece.get("text", "")
                        if isinstance(txt, dict):
                            txt = txt.get("value", "")
                        if txt:
                            answer_parts.append(txt)
                        # Per-piece citations
                        for ann in (piece.get("annotations") or []):
                            citations.append(_flatten_citation(ann))

        # Top-level / legacy fields
        for key in ("citations", "sources", "documents", "retrieval"):
            arr = data.get(key)
            if isinstance(arr, list):
                for c in arr:
                    if isinstance(c, dict):
                        citations.append(_flatten_citation(c))

        # Some envelopes return {"choices":[{"message":{"content":"..."}}]}
        for ch in (data.get("choices") or []):
            msg = ch.get("message") or {}
            txt = msg.get("content")
            if isinstance(txt, str) and txt:
                answer_parts.append(txt)

        return "\n\n".join(answer_parts).strip(), citations

    def _resolve_citation(self, c: dict) -> Optional[dict]:
        doc_id = c.get("document_id") or ""
        # Try direct id match
        if doc_id:
            for d in self.docs:
                if d["document_id"] == doc_id:
                    return d
        # Try volume_path or filename hint
        for key in ("volume_path", "source_ref", "filename", "uri"):
            val = c.get(key) or ""
            if not val:
                continue
            base = val.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            if base:
                for d in self.docs:
                    if d["document_id"] == base:
                        return d
        return None


_URL_VOLUME_RE = re.compile(
    r"/Volumes/[^\s?#]*?/(?P<region>REG-[A-Z]+)/(?P<dtype>[a-z_]+)/(?P<doc>DOC-\d+)\.md"
)
_EXCERPT_TEXT_RE = re.compile(r"#:~:text=(?P<frag>[^\"'\s]+)")


def _flatten_citation(c: dict) -> dict:
    """Normalise a heterogeneous citation/annotation into a flat dict.

    Handles three common shapes:
      1. Knowledge Assistant `url_citation` annotations (type=url_citation,
         url=https://.../Volumes/<catalog>/<schema>/<vol>/<region>/<doctype>/<DOC-...>.md#:~:text=<excerpt>)
      2. Structured citation dicts with explicit document_id / source_ref.
      3. Nested `{source: {document_id, ...}}` shapes.
    """
    out: dict = {}

    # KA url_citation shape
    url = c.get("url") or ""
    if isinstance(url, str) and "/Volumes/" in url:
        m = _URL_VOLUME_RE.search(url)
        if m:
            out["document_id"] = m.group("doc")
            out["document_type"] = m.group("dtype")
            out["region_id"] = m.group("region")
            # Reconstruct a clean /Volumes path stripped of fragments + query.
            vol_path = url.split("#", 1)[0]
            if "/fs/files" in vol_path:
                vol_path = vol_path.split("/fs/files", 1)[1]
            elif "/Volumes/" in vol_path:
                vol_path = "/" + vol_path.split("/Volumes/", 1)[1]
                vol_path = "/Volumes/" + vol_path.lstrip("/").split("/Volumes/", 1)[-1] if not vol_path.startswith("/Volumes/") else vol_path
            out["volume_path"] = vol_path
        # Pull the text fragment as the excerpt.
        m2 = _EXCERPT_TEXT_RE.search(url)
        if m2:
            from urllib.parse import unquote
            out["excerpt"] = unquote(m2.group("frag")).replace("\n", " ").strip()

    # Direct fields
    for k in ("document_id", "title", "source_ref", "filename", "uri",
              "volume_path", "region_id", "document_type", "excerpt", "score"):
        if c.get(k) and k not in out:
            out[k] = c[k]

    # Title sometimes comes back as `DOC-...md` — extract the bare ID.
    title = out.get("title") or ""
    if "document_id" not in out and isinstance(title, str):
        m3 = re.search(r"(DOC-\d+)", title)
        if m3:
            out["document_id"] = m3.group(1)

    # Common nested shapes
    src = c.get("source") or c.get("document") or {}
    if isinstance(src, dict):
        for k in ("document_id", "title", "uri", "volume_path", "region_id"):
            if k in src and k not in out:
                out[k] = src[k]
    return out
