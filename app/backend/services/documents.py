"""
Document intelligence service.

Searches synthetic asset documents either via Databricks Vector Search (when
configured) or via a local keyword-search fallback over data/documents/**/*.md.

For the demo, the local fallback is used by default and is sufficient to
produce grounded RAG-style evidence citations for the multi-agent system.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Optional

from app.backend.config import DOCS_DIR, settings


_WORD_RE = re.compile(r"[a-zA-Z]{3,}")


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
        self._load_local()

    def _load_local(self) -> None:
        if not DOCS_DIR.exists():
            print(f"[documents] DOCS_DIR missing: {DOCS_DIR}")
            return
        for path in DOCS_DIR.rglob("*.md"):
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            rel = path.relative_to(DOCS_DIR)
            parts = rel.parts
            region_id = parts[0] if len(parts) > 0 else ""
            doc_type = parts[1] if len(parts) > 1 else ""
            document_id = rel.stem
            # Extract asset/feeder ids from body for quick filtering.
            asset_id = ""
            feeder_id = ""
            m = re.search(r"AST-[A-Z]+-[A-Z]+-\d+", content)
            if m:
                asset_id = m.group(0)
            m2 = re.search(r"FDR-[A-Z]+-\d+", content)
            if m2:
                feeder_id = m2.group(0)
            self.docs.append({
                "document_id": document_id,
                "document_type": doc_type,
                "region_id": region_id,
                "asset_id": asset_id,
                "feeder_id": feeder_id,
                "title": self._extract_title(content) or document_id,
                "content": content,
                "volume_path": f"{settings.volume_path}/{rel.as_posix()}",
            })
        print(f"[documents] indexed {len(self.docs)} local markdown documents")

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
