"""
AI 서버 품질 모니터링 및 버전 관리 모듈

설계서 요구사항:
  - 오류 로그 수집, 응답시간/오류율 모니터링
  - 운영 대시보드용 통계 제공
  - 모델/룰 버전 확인, 품목 사전 갱신, 프롬프트 관리
"""

from __future__ import annotations

import time
import json
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


_LABELS_DIR = Path(__file__).resolve().parent / "data" / "labels"


class QualityMonitor:
    """AI 서버 품질 모니터링 및 버전 관리."""

    def __init__(self):
        self._request_log: deque = deque(maxlen=10000)
        self._error_log: deque = deque(maxlen=5000)
        self._start_time = datetime.now()

        self._dict_version = self._detect_dict_version()
        self._model_version = "paddleocr_2.7+rule_v1"
        self._prompt_version = "qwen_prompt_v1"

        self._thresholds = {
            "ocr_confidence_min": 0.80,
            "match_similarity_min": 0.50,
            "expiry_alert_days": 3,
        }

        self._fallback_policies = {
            "ocr_timeout": {"action": "manual_input", "timeout_sec": 30},
            "gpt_unavailable": {"action": "rule_based_fallback"},
            "low_confidence": {"action": "review_queue", "threshold": 0.60},
        }

    def _detect_dict_version(self) -> str:
        path = _LABELS_DIR / "unified_ingredients.json"
        if path.exists():
            stat = path.stat()
            ts = datetime.fromtimestamp(stat.st_mtime).strftime("%Y%m%d")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    count = len(json.load(f))
                return f"dict_v1_{ts}_{count}items"
            except Exception:
                pass
        return "dict_v1_unknown"

    # ─── 요청 로깅 ────────────────────────────────────────

    def log_request(
        self, endpoint: str, elapsed_ms: float,
        status_code: int = 200, error: Optional[str] = None,
        trace_id: Optional[str] = None,
    ):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "endpoint": endpoint,
            "elapsed_ms": round(elapsed_ms, 2),
            "status_code": status_code,
            "trace_id": trace_id or "",
        }
        self._request_log.append(entry)

        if error or status_code >= 400:
            self._error_log.append({
                **entry,
                "error": error or f"HTTP {status_code}",
            })

    # ─── 품질 지표 ────────────────────────────────────────

    def get_metrics(self, window: str = "1h") -> Dict[str, Any]:
        now = datetime.now()
        window_sec = self._parse_window(window)
        cutoff = now.timestamp() - window_sec

        recent = [
            r for r in self._request_log
            if datetime.fromisoformat(r["timestamp"]).timestamp() > cutoff
        ]

        if not recent:
            return {
                "window": window,
                "total_requests": 0,
                "error_count": 0,
                "error_rate": 0.0,
                "avg_response_ms": 0.0,
                "p95_response_ms": 0.0,
                "endpoints": {},
            }

        total = len(recent)
        errors = sum(1 for r in recent if r["status_code"] >= 400)
        elapsed_vals = sorted(r["elapsed_ms"] for r in recent)
        avg_ms = sum(elapsed_vals) / len(elapsed_vals)
        p95_idx = int(len(elapsed_vals) * 0.95)
        p95_ms = elapsed_vals[min(p95_idx, len(elapsed_vals) - 1)]

        ep_stats: Dict[str, Dict] = defaultdict(lambda: {"count": 0, "errors": 0, "total_ms": 0.0})
        for r in recent:
            ep = r["endpoint"]
            ep_stats[ep]["count"] += 1
            ep_stats[ep]["total_ms"] += r["elapsed_ms"]
            if r["status_code"] >= 400:
                ep_stats[ep]["errors"] += 1

        endpoints = {}
        for ep, st in ep_stats.items():
            endpoints[ep] = {
                "count": st["count"],
                "errors": st["errors"],
                "avg_ms": round(st["total_ms"] / st["count"], 2) if st["count"] else 0,
            }

        return {
            "window": window,
            "total_requests": total,
            "error_count": errors,
            "error_rate": round(errors / total, 4) if total else 0,
            "avg_response_ms": round(avg_ms, 2),
            "p95_response_ms": round(p95_ms, 2),
            "endpoints": endpoints,
        }

    def get_drift(self, window: str = "7d") -> Dict[str, Any]:
        metrics = self.get_metrics(window)
        status = "normal"
        if metrics["error_rate"] > 0.1:
            status = "degraded"
        if metrics["error_rate"] > 0.3:
            status = "critical"
        if metrics["p95_response_ms"] > 5000:
            status = "slow"

        return {
            "status": status,
            "window": window,
            "error_rate": metrics["error_rate"],
            "p95_response_ms": metrics["p95_response_ms"],
            "total_requests": metrics["total_requests"],
        }

    # ─── 버전 관리 ────────────────────────────────────────

    def get_dict_version(self) -> Dict[str, Any]:
        return {
            "version": self._dict_version,
            "path": str(_LABELS_DIR / "unified_ingredients.json"),
            "updated_at": datetime.now().isoformat(),
        }

    def get_model_version(self) -> Dict[str, Any]:
        return {
            "version": self._model_version,
            "components": {
                "ocr": "PaddleOCR 2.7",
                "normalizer": "rule_based_v1",
                "recommender": "weighted_scoring_v1",
                "expiry": "gpt-4o-mini + rule_fallback",
            },
        }

    def get_prompt_version(self) -> Dict[str, Any]:
        return {
            "version": self._prompt_version,
            "templates": {
                "ocr_refinement": "qwen_receipt_v1",
                "expiry_calculation": "gpt4omini_expiry_v1",
                "recommendation_explanation": "qwen_explain_v1",
            },
        }

    # ─── Threshold / Fallback 관리 ────────────────────────

    def get_thresholds(self) -> Dict[str, Any]:
        return dict(self._thresholds)

    def update_thresholds(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        self._thresholds.update(updates)
        return dict(self._thresholds)

    def get_fallback_policies(self) -> Dict[str, Any]:
        return dict(self._fallback_policies)

    def update_fallback_policy(self, policy_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if policy_id not in self._fallback_policies:
            return None
        self._fallback_policies[policy_id].update(updates)
        return {policy_id: self._fallback_policies[policy_id]}

    # ─── 오류 로그 ────────────────────────────────────────

    def get_recent_errors(self, limit: int = 50) -> List[Dict[str, Any]]:
        errors = list(self._error_log)
        errors.reverse()
        return errors[:limit]

    # ─── 유틸 ─────────────────────────────────────────────

    @staticmethod
    def _parse_window(window: str) -> float:
        unit = window[-1].lower()
        try:
            val = int(window[:-1])
        except ValueError:
            val = 1
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return val * multipliers.get(unit, 3600)

    def get_uptime(self) -> str:
        delta = datetime.now() - self._start_time
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"
