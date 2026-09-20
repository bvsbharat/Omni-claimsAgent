"""Amazon Textract OCR for ClaimPilot document uploads.

Customers can upload documents to a claim — a police report, a repair estimate,
a driver's license, an insurance card. Those land in S3 (via AWS End User
Messaging). This module extracts their text + form fields with Amazon Textract:

  - images / single-page      -> AnalyzeDocument (synchronous, from S3 object)
  - multi-page PDFs           -> StartDocumentAnalysis -> poll GetDocumentAnalysis

Returns plain extracted text plus detected key/value form pairs, which the
caller (media.py) hands to Bedrock to pull the claim-relevant fields.

Best-effort: any failure is logged and returned as empty, never raised, so the
claim flow is never broken by OCR.
"""
from __future__ import annotations

import os
import time
from typing import Any

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
_textract = boto3.client("textract", region_name=REGION)

# Textract FeatureTypes: FORMS gives key/value pairs; TABLES gives tabular data.
_FEATURES = ["FORMS", "TABLES"]


def _lines_and_pairs(blocks: list[dict]) -> dict:
    """Turn Textract blocks into {text, pairs:{k:v}} using block relationships."""
    by_id = {b["Id"]: b for b in blocks}

    def words(block) -> str:
        out = []
        for rel in block.get("Relationships", []) or []:
            if rel["Type"] == "CHILD":
                for cid in rel["Ids"]:
                    c = by_id.get(cid, {})
                    if c.get("BlockType") == "WORD":
                        out.append(c.get("Text", ""))
                    elif c.get("BlockType") == "SELECTION_ELEMENT" and c.get("SelectionStatus") == "SELECTED":
                        out.append("[X]")
        return " ".join(out)

    # plain text (LINE blocks)
    lines = [b.get("Text", "") for b in blocks if b.get("BlockType") == "LINE"]

    # form key/value pairs
    pairs: dict[str, str] = {}
    keys = [b for b in blocks if b.get("BlockType") == "KEY_VALUE_SET" and "KEY" in (b.get("EntityTypes") or [])]
    for k in keys:
        key_text = words(k)
        val_text = ""
        for rel in k.get("Relationships", []) or []:
            if rel["Type"] == "VALUE":
                for vid in rel["Ids"]:
                    val_text = words(by_id.get(vid, {}))
        if key_text:
            pairs[key_text.strip().rstrip(":")] = val_text.strip()

    return {"text": "\n".join(lines).strip(), "pairs": pairs}


def analyze_image(bucket: str, key: str) -> dict:
    """Synchronous OCR for a single image / single-page doc stored in S3."""
    try:
        resp = _textract.analyze_document(
            Document={"S3Object": {"Bucket": bucket, "Name": key}},
            FeatureTypes=_FEATURES,
        )
        return _lines_and_pairs(resp.get("Blocks", []))
    except Exception as exc:  # noqa: BLE001
        print({"textractSyncError": str(exc), "key": key})
        return {"text": "", "pairs": {}}


def analyze_pdf(bucket: str, key: str, timeout_s: int = 55) -> dict:
    """Asynchronous OCR for a (possibly multi-page) PDF stored in S3."""
    try:
        start = _textract.start_document_analysis(
            DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}},
            FeatureTypes=_FEATURES,
        )
        job_id = start["JobId"]
    except Exception as exc:  # noqa: BLE001
        print({"textractStartError": str(exc), "key": key})
        return {"text": "", "pairs": {}}

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            resp = _textract.get_document_analysis(JobId=job_id)
        except Exception as exc:  # noqa: BLE001
            print({"textractGetError": str(exc)})
            return {"text": "", "pairs": {}}
        status = resp.get("JobStatus")
        if status == "SUCCEEDED":
            blocks = list(resp.get("Blocks", []))
            token = resp.get("NextToken")
            while token:  # gather all pages
                resp = _textract.get_document_analysis(JobId=job_id, NextToken=token)
                blocks.extend(resp.get("Blocks", []))
                token = resp.get("NextToken")
            return _lines_and_pairs(blocks)
        if status == "FAILED":
            print({"textractFailed": job_id})
            return {"text": "", "pairs": {}}
        time.sleep(3)
    print({"textractTimeout": job_id})
    return {"text": "", "pairs": {}}


def extract(bucket: str, key: str, mime: str) -> dict:
    """Route to sync (image) or async (pdf) OCR and return {text, pairs}."""
    if not bucket or not key:
        return {"text": "", "pairs": {}}
    if (mime or "").lower() == "application/pdf" or key.lower().endswith(".pdf"):
        return analyze_pdf(bucket, key)
    return analyze_image(bucket, key)


def summarize(ocr: dict, max_chars: int = 1500) -> str:
    """Compact the OCR result into a string for a prompt / observation."""
    parts = []
    if ocr.get("pairs"):
        kv = "; ".join(f"{k}: {v}" for k, v in list(ocr["pairs"].items())[:20] if v)
        if kv:
            parts.append(f"Form fields: {kv}")
    if ocr.get("text"):
        parts.append(f"Text: {ocr['text']}")
    return ("\n".join(parts))[:max_chars]
