"""
bedrock_service.py

Thin wrapper around Amazon Bedrock's Converse API for the two Bedrock-backed
features in the project brief:

  1. Allergen extraction from a free-text dish description (Step 1 of the
     "Two-Step AI Chain" - no knowledge base / RAG lookup is used, per
     project scope; the model is grounded purely with the PEAL category
     list passed in the prompt).
  2. Context-aware multilingual translation of dish name + description
     into Spanish, German, Japanese and Mandarin (Step 2).

If AWS credentials / Bedrock access are not available (e.g. running the
app locally without an AWS account, or the model hasn't been granted
access yet in this account/region), every function here degrades to a
clearly-labelled offline stub so the rest of the app - UI, DynamoDB,
S3, allergen rules engine - can still be exercised end to end.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Dict, List

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .allergen_rules import PEAL_CATEGORIES
from .allergen_service import CONFIRMED, POSSIBLE, UNKNOWN

logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0"
)
LOCAL_MODE = os.environ.get("LOCAL_MODE", "false").lower() == "true"

LANGUAGES = {
    "es": "Spanish",
    "de": "German",
    "ja": "Japanese",
    "zh": "Mandarin Chinese (Simplified)",
}

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    return _client


def _converse(system_prompt: str, user_prompt: str, max_tokens: int = 700) -> str:
    client = _get_client()
    response = client.converse(
        modelId=BEDROCK_MODEL_ID,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
    )
    return response["output"]["message"]["content"][0]["text"]


def _extract_json(raw: str) -> dict:
    """Bedrock models sometimes wrap JSON in prose or code fences - strip it."""
    raw = raw.strip()
    if "```" in raw:
        raw = raw.split("```")[1] if raw.count("```") >= 2 else raw
        raw = raw.replace("json", "", 1).strip() if raw.lower().startswith("json") else raw
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    return json.loads(raw)


# --------------------------------------------------------------------------- #
# Bedrock Function Calling / Tool Use (AWS Mentor task Phases 3, 7)
#
# The Allergen Extraction step is driven through a real Bedrock tool-use call:
# the model must emit a `tool_use` with a structured `input` matching our JSON
# Schema, instead of free-form prose. Enforcing the schema here (rather than
# relying on a loose prompt) is how we keep the LLM's output shaped as
# per-allergen records with evidence + status + confidence.
# --------------------------------------------------------------------------- #

_ALLERGEN_STATUSES = [CONFIRMED, POSSIBLE, UNKNOWN]

_EXTRACT_ALLERGEN_TOOL = {
    "toolSpec": {
        "name": "extract_allergens",
        "description": (
            "Analyze a dish (name + description) and return the regulated "
            "allergens present. Each allergen must carry the exact ingredient "
            "evidence from the text, a status (CONFIRMED if there is explicit "
            "evidence, POSSIBLE if it is inferred, UNKNOWN if it cannot be "
            "determined), and a confidence 0.0-1.0. Do not invent ingredients "
            "that are not in the dish text. Name tree nuts individually "
            "(e.g. 'Cashew', 'Almond'), never a generic 'Nuts'."
        ),
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "dish_name": {"type": "string",
                                  "description": "the dish name analyzed"},
                    "allergens": {
                        "type": "array",
                        "description": "regulated allergens found in the dish",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string",
                                         "description": "canonical allergen entity/category"},
                                "evidence": {"type": "string",
                                             "description": "exact ingredient text from the dish that supports this allergen"},
                                "status": {"type": "string",
                                           "enum": _ALLERGEN_STATUSES,
                                           "description": "certainty tier"},
                                "confidence": {"type": "number",
                                               "minimum": 0,
                                               "maximum": 1,
                                               "description": "0.0-1.0"},
                                "reason": {"type": "string",
                                           "description": "optional justification, especially why POSSIBLE"},
                            },
                            "required": ["name", "evidence", "status"],
                        },
                    },
                },
                "required": ["dish_name", "allergens"],
            }
        },
    },
}


def _converse_tool_use(system_prompt: str, user_prompt: str,
                       tool: dict, max_tokens: int = 1000) -> dict:
    """Invoke Bedrock Converse with a tool, returning the parsed `toolUse.input`."""
    client = _get_client()
    response = client.converse(
        modelId=BEDROCK_MODEL_ID,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": user_prompt}]}],
        toolConfig={
            "tools": [tool],
            "toolChoice": {"auto": {}},
        },
        inferenceConfig={"maxTokens": max_tokens, "temperature": 0},
    )
    content = response["output"]["message"]["content"]
    for block in content:
        if "toolUse" in block:
            return block["toolUse"].get("input") or {}
    # Model returned no tool use - surface the raw text for diagnostics.
    text = " ".join(b.get("text", "") for b in content if "text" in b)
    raise ValueError(f"no toolUse in model response: {text[:300]}")


def extract_allergens_tool_use(dish_name: str, description: str) -> Dict:
    """Function-call driven allergen extraction (task Phase 3 / 7).

    Uses Bedrock tool-use so the model MUST return a structured `toolUse.input`
    with per-allergen name/evidence/status/confidence. Degrades to the
    deterministic keyword engine when Bedrock is unavailable or the model
    output is unusable, so the pipeline never hard-fails.

    Returns:
        {
            "dish_name": ...,
            "allergens": [{"name": ..., "evidence": ..., "status": ..., "confidence": ...}],
            "reasoning": str,
            "source": "bedrock-tool-use" | "offline",
            "error": str,     # only present on degradation
        }
    """
    if LOCAL_MODE:
        return _offline_extract_allergens_tool_use(dish_name, description)

    system_prompt = (
        "You are a food-safety compliance assistant for New Zealand "
        "restaurants, checking dishes against the FSANZ Standard 1.2.3 "
        "mandatory declarable allergen list. Use the provided tool "
        "'extract_allergens' and its schema. Only choose allergen names from "
        f"this exact NZ PEAL list: {PEAL_CATEGORIES}. "
        "Do not invent ingredients that are not present in the dish name or "
        "description. If uncertain, set status to POSSIBLE rather than "
        "CONFIRMED. Err toward declaring an allergen if there is genuine "
        "doubt (under-declaring is unsafe)."
    )
    user_prompt = f"Dish name: {dish_name}\nDescription: {description}"
    try:
        result = _converse_tool_use(system_prompt, user_prompt, _EXTRACT_ALLERGEN_TOOL)
        allergens = [
            {
                "name": str(a.get("name", "")).strip(),
                "evidence": str(a.get("evidence", "")).strip(),
                "status": a.get("status", POSSIBLE)
                           if a.get("status") in _ALLERGEN_STATUSES else POSSIBLE,
                "confidence": float(a.get("confidence") or 0.0),
                "reason": str(a.get("reason", "")).strip(),
            }
            for a in (result.get("allergens") or [])
            if a and a.get("name")
        ]
        return {
            "dish_name": result.get("dish_name", (dish_name or "").strip()),
            "allergens": allergens,
            "source": "bedrock-tool-use",
        }
    except (BotoCoreError, ClientError, ValueError, json.JSONDecodeError,
            KeyError, IndexError, TypeError) as exc:
        logger.warning("Bedrock tool-use extraction failed, using offline fallback: %s", exc)
        out = _offline_extract_allergens_tool_use(dish_name, description)
        out["error"] = str(exc)
        return out


def _offline_extract_allergens_tool_use(dish_name: str, description: str) -> Dict:
    from .allergen_service import extract_allergens_deterministic
    res = extract_allergens_deterministic(dish_name, description)
    return {
        "dish_name": res.dish_name,
        "allergens": [
            {
                "name": a.name,
                "evidence": a.evidence,
                "status": a.status,
                "confidence": a.confidence,
                "reason": a.reason,
            }
            for a in res.allergens
        ],
        "reasoning": "offline tool-use fallback (Bedrock unavailable)",
        "source": "offline",
    }


def extract_allergens(dish_name: str, description: str) -> Dict:
    """Return {'categories': [...], 'reasoning': str} using the Bedrock LLM.

    Falls back to a local (non-AI) result if Bedrock is unreachable, so the
    caller can always merge this with the deterministic rules-engine pass.
    """
    if LOCAL_MODE:
        return _offline_extract_allergens(dish_name, description)

    system_prompt = (
        "You are a food-safety compliance assistant for New Zealand "
        "restaurants, checking dishes against the FSANZ Standard 1.2.3 "
        "mandatory declarable allergen list. Only choose categories from "
        f"this exact list: {PEAL_CATEGORIES}. "
        "Respond with ONLY a JSON object, no prose, no markdown fences, "
        'in the form {"categories": ["..."], "reasoning": "..."}. '
        "If uncertain whether an ingredient is present, err on the side "
        "of including the category (under-declaring an allergen is unsafe)."
    )
    user_prompt = f"Dish name: {dish_name}\nDescription: {description}"
    try:
        raw = _converse(system_prompt, user_prompt)
        parsed = _extract_json(raw)
        categories = [c for c in parsed.get("categories", []) if c in PEAL_CATEGORIES]
        return {"categories": categories, "reasoning": parsed.get("reasoning", ""), "source": "bedrock"}
    except (BotoCoreError, ClientError, json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.warning("Bedrock allergen extraction failed, using offline fallback: %s", exc)
        result = _offline_extract_allergens(dish_name, description)
        result["error"] = str(exc)
        return result


def _offline_extract_allergens(dish_name: str, description: str) -> Dict:
    from .allergen_rules import scan_text_for_allergens
    categories = scan_text_for_allergens(f"{dish_name} {description}")
    return {"categories": categories, "reasoning": "offline keyword fallback (Bedrock unavailable)", "source": "offline"}


def translate_dish(dish_name: str, description: str) -> Dict[str, Dict[str, str]]:
    """Translate name+description into all configured LANGUAGES.

    Returns { 'es': {'name': ..., 'description': ...}, 'de': {...}, ... }
    """
    if LOCAL_MODE:
        return _offline_translate(dish_name, description)

    system_prompt = (
        "You are a professional culinary translator for restaurant menus "
        "shown to international tourists in New Zealand. Preserve the "
        "meaning of culinary terms (e.g. keep 'chowder', 'ribeye' style "
        "naming conventions native speakers would recognise; do not "
        "invent ingredients that were not mentioned). "
        "Respond with ONLY a JSON object, no prose, no markdown fences, "
        "mapping each language code to {\"name\": ..., \"description\": ...}. "
        f"Language codes and names: {LANGUAGES}"
    )
    user_prompt = f"Dish name: {dish_name}\nDescription: {description}"
    try:
        raw = _converse(system_prompt, user_prompt, max_tokens=900)
        parsed = _extract_json(raw)
        result = {}
        for code in LANGUAGES:
            entry = parsed.get(code, {})
            result[code] = {
                "name": entry.get("name", dish_name),
                "description": entry.get("description", description),
            }
        return result
    except (BotoCoreError, ClientError, json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.warning("Bedrock translation failed, trying Amazon Translate fallback: %s", exc)
        return _translate_fallback(dish_name, description, str(exc))


def _translate_fallback(dish_name: str, description: str, bedrock_error: str) -> Dict:
    """Second-line fallback: Amazon Translate (plain MT, no culinary context
    preservation) - only used if the Bedrock call itself fails."""
    try:
        client = boto3.client("translate", region_name=AWS_REGION)
        result = {}
        for code in LANGUAGES:
            name = client.translate_text(
                Text=dish_name, SourceLanguageCode="en", TargetLanguageCode=code
            )["TranslatedText"]
            desc = client.translate_text(
                Text=description, SourceLanguageCode="en", TargetLanguageCode=code
            )["TranslatedText"]
            result[code] = {"name": name, "description": desc, "engine": "amazon_translate_fallback"}
        return result
    except (BotoCoreError, ClientError) as exc:
        logger.warning("Amazon Translate fallback also failed, using offline stub: %s", exc)
        stub = _offline_translate(dish_name, description)
        stub["_error"] = f"bedrock: {bedrock_error}; translate: {exc}"
        return stub


def _offline_translate(dish_name: str, description: str) -> Dict:
    return {
        code: {
            "name": f"[{lang} - offline] {dish_name}",
            "description": f"[{lang} translation unavailable offline] {description}",
        }
        for code, lang in LANGUAGES.items()
    }
