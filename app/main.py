from __future__ import annotations

import json
import os
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "knowledge_base.json"
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG: list[dict[str, Any]] = []

app = FastAPI(title="SSD/NAND Firmware Knowledge Assistant", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


class QuestionPayload(BaseModel):
    question: str
    top_k: int = 4


with DATA_FILE.open("r", encoding="utf-8") as handle:
    KNOWLEDGE_BASE: list[dict[str, Any]] = json.load(handle)


SUBSYSTEM_KEYWORDS = {
    "Host": {"host", "queue", "nvme", "pcie", "command", "timeout", "resume", "power", "plr"},
    "FTL": {"ftl", "mapping", "garbage", "collection", "wear", "leveling", "block", "refresh"},
    "NAND": {"nand", "ecc", "retry", "read", "erase", "bad", "cell", "margin", "retention"},
    "Hardware": {"thermal", "temperature", "reset", "voltage", "board", "connector", "power"},
}


ACTION_GUIDANCE = {
    "Host": [
        "Check host command queue, timeout timestamps, and reset flow around the failure window.",
        "Compare host-side behavior against the previous stable firmware and the same workload profile.",
    ],
    "FTL": [
        "Review mapping-table changes, garbage-collection pressure, and free-block availability.",
        "Compare wear-leveling and block retirement thresholds across firmware versions.",
    ],
    "NAND": [
        "Inspect ECC trend, read-retry counters, bad-block growth, and erase-cycle distribution.",
        "Run an A/B check against healthy units from the same NAND lot and firmware version.",
    ],
    "Hardware": [
        "Correlate reset timestamps with temperature, voltage, and workload spikes.",
        "Inspect board-level conditions, cooling path, and connector or power stability.",
    ],
    "Unknown": [
        "Collect additional logs, firmware version, workload profile, and affected unit history.",
        "Avoid assigning root cause until stronger evidence is retrieved.",
    ],
}


OWNER_TEAMS = {
    "Host": "Firmware Host Interface",
    "FTL": "Firmware FTL",
    "NAND": "NAND Reliability",
    "Hardware": "Hardware Validation",
    "Unknown": "Reliability Triage",
}


REQUIRED_EVIDENCE = {
    "Host": [
        "host command trace with timestamps",
        "NVMe/USB/eMMC command timeout counters",
        "firmware version and host workload profile",
    ],
    "FTL": [
        "free-block pool trend",
        "garbage-collection latency trace",
        "mapping-table and wear-leveling change notes",
    ],
    "NAND": [
        "ECC correction trend by block/page",
        "read-retry counter distribution",
        "NAND lot, erase-cycle, and retention history",
    ],
    "Hardware": [
        "temperature and voltage timeline",
        "reset reason register dump",
        "board/power/cooling inspection notes",
    ],
    "Unknown": [
        "full failure log bundle",
        "affected unit history",
        "firmware version, workload, and reproduction steps",
    ],
}


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+", text.lower())


def enrich_entry(entry: dict[str, Any], index: int) -> dict[str, Any]:
    enriched = dict(entry)
    enriched.setdefault("id", f"kb_{index:03d}")
    enriched.setdefault("topic", "Unknown")
    enriched.setdefault("source", "knowledge_base.json")
    enriched.setdefault("content", "")
    enriched.setdefault("title", f"Knowledge Note {index}")
    enriched.setdefault("revision", "demo")
    return enriched


KNOWLEDGE_BASE = [enrich_entry(entry, index) for index, entry in enumerate(KNOWLEDGE_BASE, start=1)]


def classify_subsystem(text: str) -> str:
    tokens = set(tokenize(text))
    scores = {
        subsystem: len(tokens.intersection(keywords))
        for subsystem, keywords in SUBSYSTEM_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Unknown"


def score_entry(question: str, entry: dict[str, Any]) -> int:
    question_tokens = set(tokenize(question))
    entry_tokens = set(tokenize(f"{entry['title']} {entry['topic']} {entry['content']}"))
    overlap = len(question_tokens.intersection(entry_tokens))
    phrase_boost = 0
    lower_question = question.lower()
    for phrase in ["read retry", "wear leveling", "garbage collection", "power loss", "controller reset"]:
        if phrase in lower_question and phrase in entry["content"].lower():
            phrase_boost += 3
    if classify_subsystem(question) == entry.get("topic"):
        phrase_boost += 2
    return overlap + phrase_boost


def retrieve(question: str, limit: int = 4) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in KNOWLEDGE_BASE:
        score = score_entry(question, entry)
        if score:
            scored.append((score, {**entry, "retrieval_score": score}))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in scored[:limit]]


def evidence_quality(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    if not contexts:
        return {"level": "insufficient", "confidence": 0.1, "reason": "No relevant notes retrieved"}
    top_score = max(item["retrieval_score"] for item in contexts)
    if top_score >= 8:
        return {"level": "strong", "confidence": 0.86, "reason": "Multiple strong keyword and topic matches"}
    if top_score >= 4:
        return {"level": "moderate", "confidence": 0.62, "reason": "Relevant notes found, but evidence should be verified"}
    return {"level": "weak", "confidence": 0.35, "reason": "Only weak evidence matched the question"}


def build_trace_id(question: str) -> str:
    digest = hashlib.sha1(question.strip().lower().encode("utf-8")).hexdigest()[:8].upper()
    return f"QA-{digest}"


def build_investigation_runbook(
    question: str,
    contexts: list[dict[str, Any]],
    subsystem: str,
    quality: dict[str, Any],
) -> dict[str, Any]:
    evidence_titles = [item["title"] for item in contexts[:3]]
    return {
        "objective": "Turn the symptom into a reproducible firmware investigation with cited evidence.",
        "owner_team": OWNER_TEAMS[subsystem],
        "likely_subsystem": subsystem,
        "evidence_level": quality["level"],
        "required_evidence": REQUIRED_EVIDENCE[subsystem],
        "debug_sequence": [
            "Confirm firmware version, NAND lot, workload, and exact failure timestamp.",
            "Compare the affected unit against a healthy unit from the same cohort.",
            *ACTION_GUIDANCE[subsystem],
        ],
        "evidence_used": evidence_titles,
        "exit_criteria": [
            "Root-cause hypothesis is linked to a cited log, note, or metric.",
            "A reproduction or A/B comparison exists before firmware action is recommended.",
            "Owner team signs off on next validation step.",
        ],
        "question": question,
    }


def build_risk_controls(quality: dict[str, Any], citations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "grounding_policy": "context-only",
        "evidence_level": quality["level"],
        "citation_count": len(citations),
        "hallucination_guard": "Answer must say when evidence is insufficient.",
        "review_required": quality["level"] in {"weak", "insufficient"},
    }


def record_audit_event(
    trace_id: str,
    question: str,
    subsystem: str,
    quality: dict[str, Any],
    citations: list[dict[str, Any]],
) -> dict[str, Any]:
    event = {
        "trace_id": trace_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "likely_subsystem": subsystem,
        "evidence_level": quality["level"],
        "confidence": quality["confidence"],
        "citation_titles": [item["title"] for item in citations],
        "owner_team": OWNER_TEAMS[subsystem],
    }
    AUDIT_LOG.append(event)
    del AUDIT_LOG[:-50]
    return event


def read_upload_text(upload: UploadFile, raw: bytes) -> str:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in {".txt", ".md", ".log", ".csv", ".json"}:
        raise ValueError("Only TXT, MD, LOG, CSV, and JSON uploads are supported in this MVP")
    return raw.decode("utf-8", errors="ignore")


def chunk_text(text: str, size: int = 1200) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    return [normalized[index : index + size] for index in range(0, len(normalized), size)]


def get_openai_client() -> Any | None:
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        return None
    return OpenAI()


def fallback_answer(question: str, contexts: list[dict[str, Any]], subsystem: str, quality: dict[str, Any]) -> str:
    if quality["level"] == "insufficient":
        return (
            "Evidence is insufficient for a grounded answer. Upload the relevant firmware note, "
            "validation log, RMA summary, or datasheet section before assigning root cause."
        )
    bullets = " ".join(
        f"{item['title']}: {item['content'][:180].strip()}..." for item in contexts
    )
    return (
        f"Question: {question}\n\n"
        f"Likely subsystem: {subsystem}. Evidence quality: {quality['level']}. "
        f"Based on the retrieved firmware notes, the most relevant guidance is: {bullets} "
        f"Recommended next step: {ACTION_GUIDANCE[subsystem][0]}"
    )


def answer_question(question: str, contexts: list[dict[str, Any]], subsystem: str, quality: dict[str, Any]) -> str:
    client = get_openai_client()
    if client is None:
        return fallback_answer(question, contexts, subsystem, quality)

    prompt = {
        "question": question,
        "likely_subsystem": subsystem,
        "evidence_quality": quality,
        "contexts": contexts,
        "instructions": (
            "Answer like a firmware knowledge assistant for SSD and NAND controller teams. "
            "Only use the provided context. Be concise, cite the relevant note titles inline, "
            "state evidence strength, and explicitly say when evidence is incomplete. "
            "End with a concrete validation or debugging next step."
        ),
    }
    response = client.responses.create(model=DEFAULT_MODEL, input=json.dumps(prompt))
    return response.output_text.strip()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"document_count": len(KNOWLEDGE_BASE), "model_name": DEFAULT_MODEL},
    )


@app.get("/api/knowledge")
async def list_knowledge() -> JSONResponse:
    return JSONResponse({"documents": KNOWLEDGE_BASE, "model_name": DEFAULT_MODEL})


@app.post("/api/ask")
async def ask_question(payload: QuestionPayload) -> JSONResponse:
    contexts = retrieve(payload.question, max(1, min(payload.top_k, 8)))
    combined_text = f"{payload.question} " + " ".join(item["content"] for item in contexts)
    subsystem = classify_subsystem(combined_text)
    quality = evidence_quality(contexts)
    answer = answer_question(payload.question, contexts, subsystem, quality)
    trace_id = build_trace_id(payload.question)
    citations = [
        {
            "title": item["title"],
            "source": item["source"],
            "topic": item["topic"],
            "score": item["retrieval_score"],
        }
        for item in contexts
    ]
    audit_event = record_audit_event(trace_id, payload.question, subsystem, quality, citations)
    return JSONResponse(
        {
            "trace_id": trace_id,
            "answer": answer,
            "citations": citations,
            "likely_subsystem": subsystem,
            "evidence_quality": quality,
            "recommended_actions": ACTION_GUIDANCE[subsystem],
            "investigation_runbook": build_investigation_runbook(payload.question, contexts, subsystem, quality),
            "risk_controls": build_risk_controls(quality, citations),
            "audit_event": audit_event,
        }
    )


@app.post("/api/upload")
async def upload_knowledge(
    file: UploadFile = File(...),
    topic: str = Form("Unknown"),
    title: str = Form("Uploaded Engineering Note"),
) -> JSONResponse:
    raw = await file.read()
    try:
        text = read_upload_text(file, raw)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

    safe_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", file.filename or "upload.txt")
    saved_path = UPLOAD_DIR / safe_name
    saved_path.write_bytes(raw)

    chunks = chunk_text(text)
    new_entries = []
    for index, chunk in enumerate(chunks, start=1):
        new_entries.append(
            enrich_entry(
                {
                    "title": f"{title} - chunk {index}",
                    "topic": topic,
                    "source": safe_name,
                    "content": chunk,
                    "revision": "uploaded",
                },
                len(KNOWLEDGE_BASE) + index,
            )
        )
    KNOWLEDGE_BASE.extend(new_entries)
    return JSONResponse(
        {
            "status": "indexed",
            "source": safe_name,
            "chunks": len(new_entries),
            "documents_loaded": len(KNOWLEDGE_BASE),
        }
    )


@app.get("/api/audit-log")
async def audit_log() -> JSONResponse:
    return JSONResponse(
        {
            "events": list(reversed(AUDIT_LOG[-25:])),
            "retention_policy": "in-memory demo audit trail",
            "max_events": 50,
        }
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "audit_events": str(len(AUDIT_LOG))}
