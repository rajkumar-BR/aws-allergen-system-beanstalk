"""
application.py

Elastic Beanstalk entry point. The Procfile runs:
    gunicorn --workers=3 --bind 127.0.0.1:8000 application:application

This single Flask app replaces the Amplify + API Gateway + Lambda chain
from the original architecture proposal: Beanstalk's EC2 instances run
this app directly, so the "Step 1 (Analyze & Compliance) / Step 2
(Translate)" two-step chain is just two function calls inside one
request handler instead of two separate Lambda invocations.

Per project scope: no knowledge-base / RAG lookup is used anywhere in
this app - allergen compliance is a deterministic rules engine
(services/allergen_rules.py) reconciled against a Bedrock LLM pass with
the category list embedded directly in the prompt.
"""
from __future__ import annotations
import json
import logging
import os

from flask import Flask, jsonify, request, send_from_directory

from services import (
    allergen_rules,
    allergen_service,
    bedrock_service,
    compliance_service,
    dynamo_service,
    rag_service,
    s3_service,
    textract_service,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
SAMPLE_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "sample_data", "sample_menu.json"
)

application = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")
app = application  # alias - some tooling/tests look for `app`

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
application.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES


# ---------------------------------------------------------------- static UI
@application.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@application.route("/health")
def health():
    return jsonify({"status": "ok", "local_mode": os.environ.get("LOCAL_MODE", "false")})


# ---------------------------------------------------------------- reference data
@application.route("/api/allergen-categories")
def allergen_categories():
    return jsonify({"categories": allergen_rules.PEAL_CATEGORIES})


@application.route("/api/languages")
def languages():
    return jsonify({"languages": bedrock_service.LANGUAGES})


# ------------------------------------------------ allergen & compliance API
def _dish_from_json(body: dict) -> tuple:
    """Extract (dish_name, description) from a request body, accepting both
    the new 'dish_name' field and the legacy 'name' field used elsewhere."""
    name = (body.get("dish_name") or body.get("name") or "").strip()
    description = (body.get("description") or "").strip()
    return name, description


def _new_request_id() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


@application.route("/api/allergens/extract", methods=["POST"])
def allergens_extract():
    """Task Phase 13 Endpoint 1 — Allergen Extraction.

    POST {"dish_name": "...", "description": "..."}
      -> {"dish_name": "...", "allergens": [{name, evidence, status, confidence}]}
    """
    import time
    request_id = _new_request_id()
    started = time.time()
    body = request.get_json(silent=True) or {}
    name, description = _dish_from_json(body)
    if not name:
        return jsonify({"error": "dish_name (or name) is required"}), 400
    try:
        result = allergen_service.extract(name, description)
        logger.info(
            "allergens/extract request_id=%s dish=%r allergens=%d latency_ms=%.0f",
            request_id, name, len(result.allergens), (time.time() - started) * 1000,
        )
        return jsonify(result.to_json())
    except Exception as exc:  # noqa: BLE001 - surface as a 500, never a fake result
        logger.error("allergens/extract request_id=%s failed: %s", request_id, exc)
        return jsonify({"error": "extraction failed", "detail": str(exc)}), 500


@application.route("/api/compliance/verify", methods=["POST"])
def compliance_verify():
    """Task Phase 13 Endpoint 2 — Compliance Verification.

    POST {"dish_name": "...", "description": "...", "allergens": [...]}
      -> {"dish_name": "...", "compliance": {...}, "sources": [...]}

    If no `allergens` list is supplied, extraction runs first.
    """
    import time
    request_id = _new_request_id()
    started = time.time()
    body = request.get_json(silent=True) or {}
    name, description = _dish_from_json(body)
    if not name:
        return jsonify({"error": "dish_name (or name) is required"}), 400
    try:
        provided = body.get("allergens")
        result = allergen_service.verify(name, provided, description=description)
        logger.info(
            "compliance/verify request_id=%s dish=%r status=%s latency_ms=%.0f",
            request_id, name, result.status, (time.time() - started) * 1000,
        )
        return jsonify(result.to_json())
    except Exception as exc:  # noqa: BLE001
        logger.error("compliance/verify request_id=%s failed: %s", request_id, exc)
        return jsonify({"error": "verification failed", "detail": str(exc)}), 500


# ---------------------------------------------------------------- core pipeline
def _run_pipeline(menu_id: str, name: str, description: str, source: str) -> dict:
    """Shared pipeline: (1) allergen analyze+verify (2) translate.

    Compliance verification combines three signals: Bedrock LLM extraction,
    the deterministic NZ PEAL rules engine, and (when available) Bedrock RAG
    regulatory context via rag_service + compliance_service. The RAG layer
    degrades to the bundled kb_docs/ search when AWS is unavailable.
    """
    llm_result = bedrock_service.extract_allergens(name, description)
    rule_categories = allergen_rules.scan_text_for_allergens(f"{name} {description}")

    # Bedrock RAG + NZ PEAL compliance verification (Suresh's workstream).
    dish_text = f"{name} {description}".strip()
    retrieval = rag_service.retrieve_context(dish_text)
    compliance = compliance_service.verify_compliance(
        name,
        description,
        llm_result.get("categories", []),
        rule_categories,
        retrieval,
    )
    confirmed = compliance["confirmed"]

    translations = bedrock_service.translate_dish(name, description)

    item = {
        "menu_id": menu_id,
        "name": name,
        "description": description,
        "source": source,
        "status": "ai_verified",
        "allergens": {
            "confirmed": confirmed,
            "display_tags": allergen_rules.to_display_tags(confirmed),
            "llm_reasoning": llm_result.get("reasoning", ""),
            "llm_source": llm_result.get("source", "bedrock"),
            "disagreements": compliance["disagreements"],
            "rag_citations": compliance["citations"],
            "compliance": {
                "engine": compliance["engine"],
                "rag_categories": compliance["rag_categories"],
                "reasoning": compliance.get("reasoning", ""),
            },
        },
        "diet_tags": allergen_rules.derive_diet_tags(confirmed, f"{name} {description}"),
        "translations": translations,
    }
    return dynamo_service.put_item(item)


@application.route("/api/menus")
def get_menus():
    return jsonify({"menus": dynamo_service.list_menus()})


@application.route("/api/menus/<menu_id>/items", methods=["GET"])
def get_items(menu_id):
    return jsonify({"items": dynamo_service.list_items(menu_id)})


@application.route("/api/menus/<menu_id>/items", methods=["POST"])
def create_item(menu_id):
    body = request.get_json(force=True) or {}
    name = (body.get("name") or "").strip()
    description = (body.get("description") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    item = _run_pipeline(menu_id, name, description, source="manual")
    return jsonify({"item": item}), 201


@application.route("/api/menus/<menu_id>/items/<item_id>", methods=["PATCH"])
def update_item(menu_id, item_id):
    """Human-in-the-loop override: kitchen manager corrects allergen tags
    or translations after AI verification."""
    existing = dynamo_service.get_item(menu_id, item_id)
    if not existing:
        return jsonify({"error": "not found"}), 404

    body = request.get_json(force=True) or {}
    if "confirmed_allergens" in body:
        confirmed = [c for c in body["confirmed_allergens"] if c in allergen_rules.PEAL_CATEGORIES]
        existing["allergens"]["confirmed"] = confirmed
        existing["allergens"]["display_tags"] = allergen_rules.to_display_tags(confirmed)
        existing["diet_tags"] = allergen_rules.derive_diet_tags(confirmed)
    if "translations" in body:
        existing["translations"].update(body["translations"])
    if "name" in body:
        existing["name"] = body["name"]
    if "description" in body:
        existing["description"] = body["description"]
    existing["status"] = "human_verified"
    existing["item_id"] = item_id
    existing["menu_id"] = menu_id
    saved = dynamo_service.put_item(existing)
    return jsonify({"item": saved})


@application.route("/api/menus/<menu_id>/items/<item_id>", methods=["DELETE"])
def delete_item(menu_id, item_id):
    dynamo_service.delete_item(menu_id, item_id)
    return jsonify({"deleted": item_id})


# ---------------------------------------------------------------- upload / OCR
def _split_ocr_lines_into_dishes(lines: list[str]) -> list[dict]:
    """Very simple heuristic: treat each non-empty line as a dish name and
    the following line as its description, alternating. Real menu layouts
    vary a lot - this is a starting point matching the mock-up's
    "name + description" card format and is designed to be improved
    with the human-in-the-loop editor rather than perfected here."""
    cleaned = [l.strip() for l in lines if l.strip()]
    dishes = []
    i = 0
    while i < len(cleaned):
        name = cleaned[i]
        description = cleaned[i + 1] if i + 1 < len(cleaned) else ""
        dishes.append({"name": name, "description": description})
        i += 2
    return dishes


@application.route("/api/menus/<menu_id>/upload", methods=["POST"])
def upload_menu(menu_id):
    if "file" not in request.files:
        return jsonify({"error": "multipart file field 'file' is required"}), 400
    file = request.files["file"]
    file_bytes = file.read()
    content_type = file.content_type or "application/octet-stream"

    stored_path = s3_service.upload_raw_file(file_bytes, file.filename, content_type)
    lines = textract_service.extract_text_from_bytes(file_bytes, content_type)
    dishes = _split_ocr_lines_into_dishes(lines)

    created = []
    for dish in dishes:
        if not dish["name"]:
            continue
        item = _run_pipeline(menu_id, dish["name"], dish["description"], source="upload")
        created.append(item)

    return jsonify({"stored_path": stored_path, "ocr_lines": lines, "items": created}), 201


# ---------------------------------------------------------------- sample data
@application.route("/api/menus/<menu_id>/seed", methods=["POST"])
def seed_sample_menu(menu_id):
    """Loads sample_data/sample_menu.json and runs every dish through the
    full pipeline - used to demo the system without needing a real
    upload, and by the local smoke-test script."""
    with open(SAMPLE_DATA_PATH, "r") as f:
        sample = json.load(f)

    created = []
    for dish in sample["items"]:
        item = _run_pipeline(menu_id, dish["name"], dish["description"], source="sample")
        created.append(item)
    return jsonify({"menu_id": menu_id, "items": created}), 201


if __name__ == "__main__":
    # Local dev server only - Beanstalk uses gunicorn via the Procfile.
    application.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), debug=True)
