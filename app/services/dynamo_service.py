"""
dynamo_service.py

Persistence layer for menus/menu items and their allergen + translation
metadata. Uses DynamoDB in AWS; falls back to a local JSON file when
LOCAL_MODE=true (no AWS account needed) so the UI can be smoke-tested
before/without a real deployment.

Table design (single-table):
  PK: menu_id (str)          - e.g. "kiwi-cafe-queenstown"
  SK: item_id (str)          - e.g. "dish-0001"
  Other attributes: name, description, category, allergens (list),
                    diet_tags (list), translations (map), status,
                    updated_at, source ("sample" | "upload")
"""
from __future__ import annotations
import json
import logging
import os
import tempfile
import time
import uuid
from typing import Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

# Region resolution: a service-specific override wins, otherwise fall back to
# the shared AWS_REGION. DynamoDB is deployed in us-east-1 while Bedrock/KB is
# in ap-southeast-2, so a single AWS_REGION cannot serve both - per-service
# overrides (DYNAMODB_REGION) let the app talk to both regions at once.
AWS_REGION = os.environ.get(
    "DYNAMODB_REGION", os.environ.get("AWS_REGION", "us-east-1")
)
TABLE_NAME = os.environ.get("DYNAMODB_TABLE", "allergen-menu-items")
LOCAL_MODE = os.environ.get("LOCAL_MODE", "false").lower() == "true"
# Use the platform temp dir rather than a hardcoded /tmp so the local
# fallback also works on Windows (where /tmp does not exist as a path).
LOCAL_DB_PATH = os.environ.get(
    "LOCAL_DB_PATH", os.path.join(tempfile.gettempdir(), "allergen_local_db.json")
)

_table = None


def _get_table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb", region_name=AWS_REGION).Table(TABLE_NAME)
    return _table


# ---------------------------------------------------------------- local fallback
def _load_local() -> List[Dict]:
    if not os.path.exists(LOCAL_DB_PATH):
        return []
    with open(LOCAL_DB_PATH, "r") as f:
        return json.load(f)


def _save_local(items: List[Dict]) -> None:
    # Ensure the parent dir exists (may not exist on a fresh machine / Windows).
    os.makedirs(os.path.dirname(LOCAL_DB_PATH), exist_ok=True)
    with open(LOCAL_DB_PATH, "w") as f:
        json.dump(items, f, indent=2)


# ---------------------------------------------------------------- public API
def put_item(item: Dict) -> Dict:
    """Store item in DynamoDB (AWS) or the local JSON fallback (LOCAL_MODE)."""
    item.setdefault("item_id", f"dish-{uuid.uuid4().hex[:8]}")
    item["updated_at"] = int(time.time())

    if LOCAL_MODE:
        items = _load_local()
        items = [i for i in items if not (i["menu_id"] == item["menu_id"] and i["item_id"] == item["item_id"])]
        items.append(item)
        _save_local(items)
        return item

    if not TABLE_NAME:
        raise ValueError("DYNAMODB_TABLE environment variable is not set; cannot use AWS DynamoDB")

    _get_table().put_item(Item=item)
    return item


def list_items(menu_id: str) -> List[Dict]:
    """List items by menu_id from DynamoDB (AWS) or local JSON (LOCAL_MODE)."""
    if LOCAL_MODE:
        return [i for i in _load_local() if i["menu_id"] == menu_id]

    if not TABLE_NAME:
        raise ValueError("DYNAMODB_TABLE environment variable is not set; cannot use AWS DynamoDB")

    response = _get_table().query(KeyConditionExpression=Key("menu_id").eq(menu_id))
    return response.get("Items", [])


def get_item(menu_id: str, item_id: str) -> Optional[Dict]:
    """Get a single item from DynamoDB (AWS) or local JSON (LOCAL_MODE)."""
    if LOCAL_MODE:
        for i in _load_local():
            if i["menu_id"] == menu_id and i["item_id"] == item_id:
                return i
        return None

    if not TABLE_NAME:
        raise ValueError("DYNAMODB_TABLE environment variable is not set; cannot use AWS DynamoDB")

    response = _get_table().get_item(Key={"menu_id": menu_id, "item_id": item_id})
    return response.get("Item")


def delete_item(menu_id: str, item_id: str) -> None:
    if LOCAL_MODE:
        items = [i for i in _load_local() if not (i["menu_id"] == menu_id and i["item_id"] == item_id)]
        _save_local(items)
        return

    try:
        _get_table().delete_item(Key={"menu_id": menu_id, "item_id": item_id})
    except (BotoCoreError, ClientError) as exc:
        logger.error("DynamoDB delete_item failed: %s", exc)
        raise


def list_menus() -> List[str]:
    if LOCAL_MODE:
        return sorted({i["menu_id"] for i in _load_local()})

    try:
        response = _get_table().scan(ProjectionExpression="menu_id")
        return sorted({i["menu_id"] for i in response.get("Items", [])})
    except (BotoCoreError, ClientError) as exc:
        logger.error("DynamoDB scan failed: %s", exc)
        raise
