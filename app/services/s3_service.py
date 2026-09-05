"""
s3_service.py

Stores raw uploaded menu files (PDF/JPG/PNG) for audit/reprocessing.
Falls back to writing under /tmp when LOCAL_MODE=true.
"""
from __future__ import annotations
import logging
import os
import tempfile
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get("S3_REGION", os.environ.get("AWS_REGION", "us-east-1"))
BUCKET_NAME = os.environ.get("S3_BUCKET", "")
LOCAL_MODE = os.environ.get("LOCAL_MODE", "false").lower() == "true"
# Platform temp dir (not a hardcoded /tmp) so local uploads work on Windows too.
LOCAL_UPLOAD_DIR = os.environ.get(
    "LOCAL_UPLOAD_DIR", os.path.join(tempfile.gettempdir(), "allergen_uploads")
)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("s3", region_name=AWS_REGION)
    return _client


def upload_raw_file(file_bytes: bytes, filename: str, content_type: str) -> str:
    """Returns a storage key/path for the saved raw file (S3 or local dir)."""
    key = f"uploads/{uuid.uuid4().hex[:10]}-{filename}"

    if LOCAL_MODE:
        os.makedirs(LOCAL_UPLOAD_DIR, exist_ok=True)
        path = os.path.join(LOCAL_UPLOAD_DIR, key.replace("/", "_"))
        with open(path, "wb") as f:
            f.write(file_bytes)
        return path

    if not BUCKET_NAME:
        raise ValueError("S3_BUCKET environment variable is not set; cannot use AWS S3")

    _get_client().put_object(
        Bucket=BUCKET_NAME, Key=key, Body=file_bytes, ContentType=content_type
    )
    return f"s3://{BUCKET_NAME}/{key}"
