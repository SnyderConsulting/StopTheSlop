from __future__ import annotations

import os
from typing import Any

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.data.tables import TableServiceClient, UpdateMode
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from .common import read_text
from .config import SOURCE_BLOB_CONTAINER, TABLE_NAME

_table_client = None
_blob_container_client = None


def build_table_service_client() -> TableServiceClient:
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if connection_string:
        return TableServiceClient.from_connection_string(connection_string)

    storage_account_name = os.getenv("STORAGE_ACCOUNT_NAME", "").strip()
    if not storage_account_name:
        raise RuntimeError("Set AZURE_STORAGE_CONNECTION_STRING or STORAGE_ACCOUNT_NAME.")

    endpoint = f"https://{storage_account_name}.table.core.windows.net"
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return TableServiceClient(endpoint=endpoint, credential=credential)


def get_table_client():
    global _table_client
    if _table_client is None:
        _table_client = build_table_service_client().create_table_if_not_exists(TABLE_NAME)
    return _table_client


def build_blob_service_client() -> BlobServiceClient:
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
    if connection_string:
        return BlobServiceClient.from_connection_string(connection_string)

    storage_account_name = os.getenv("STORAGE_ACCOUNT_NAME", "").strip()
    if not storage_account_name:
        raise RuntimeError("Set AZURE_STORAGE_CONNECTION_STRING or STORAGE_ACCOUNT_NAME.")

    endpoint = f"https://{storage_account_name}.blob.core.windows.net"
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return BlobServiceClient(account_url=endpoint, credential=credential)


def get_blob_container_client():
    global _blob_container_client
    if _blob_container_client is None:
        service_client = build_blob_service_client()
        client = service_client.get_container_client(SOURCE_BLOB_CONTAINER)
        try:
            client.create_container()
        except ResourceExistsError:
            pass
        _blob_container_client = client
    return _blob_container_client


def list_rows(partition_key: str) -> list[dict[str, Any]]:
    query = f"PartitionKey eq '{partition_key}'"
    return list(get_table_client().query_entities(query_filter=query))


def get_row(partition_key: str, row_key: str) -> dict[str, Any] | None:
    try:
        return get_table_client().get_entity(partition_key=partition_key, row_key=row_key)
    except ResourceNotFoundError:
        return None


def upsert_row(entity: dict[str, Any]) -> None:
    get_table_client().upsert_entity(mode=UpdateMode.REPLACE, entity=entity)


def upload_blob_bytes(blob_path: str, payload: bytes, content_type: str) -> None:
    get_blob_container_client().upload_blob(
        name=read_text(blob_path, 1200),
        data=payload,
        overwrite=True,
        content_settings=ContentSettings(content_type=read_text(content_type, 120) or "application/octet-stream"),
    )

