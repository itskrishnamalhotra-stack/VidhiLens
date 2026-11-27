"""Clone a viewer-accessible LegalAI Drive folder into the current user's My Drive.

This source is embedded in the generated Colab notebook. It deliberately uses
the authenticated Drive API instead of a public downloader, so the owner can
share the source folder directly with a friend's Google account as Viewer.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse


DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"


def parse_drive_folder_url(url: str) -> tuple[str, str | None]:
    """Return (folder id, optional resource key) from common Drive folder URLs."""
    value = url.strip()
    match = re.search(r"/folders/([A-Za-z0-9_-]{10,})", value)
    query = parse_qs(urlparse(value).query)
    folder_id = match.group(1) if match else (query.get("id") or [""])[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{10,}", folder_id):
        raise ValueError("The shared source must be a Google Drive folder link")
    resource_key = (query.get("resourcekey") or query.get("resourceKey") or [None])[0]
    return folder_id, resource_key


def _execute(request, resource_pairs=()):
    pairs = [(item_id, key) for item_id, key in resource_pairs if key]
    if pairs:
        request.headers["X-Goog-Drive-Resource-Keys"] = ",".join(
            f"{item_id}/{key}" for item_id, key in pairs)
    return request.execute()


def _list_children(service, folder_id: str, resource_key: str | None = None) -> list[dict]:
    children = []
    page_token = None
    while True:
        request = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields=("nextPageToken,files(id,name,mimeType,size,md5Checksum,"
                    "resourceKey,capabilities(canCopy))"),
            pageSize=1000,
            pageToken=page_token,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        response = _execute(request, [(folder_id, resource_key)])
        children.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return sorted(children, key=lambda item: (item["mimeType"] != DRIVE_FOLDER_MIME,
                                                       item["name"], item["id"]))


def _same_blob(source: dict, target: dict) -> bool:
    source_md5 = source.get("md5Checksum")
    target_md5 = target.get("md5Checksum")
    if source_md5 and target_md5:
        return source_md5 == target_md5 and source.get("size") == target.get("size")
    return source.get("size") is not None and source.get("size") == target.get("size")


def _copy_tree(service, source_id: str, destination_id: str,
               source_resource_key: str | None = None) -> dict[str, int]:
    counts = {"folders_created": 0, "files_copied": 0, "files_already_present": 0}
    destination_children = _list_children(service, destination_id)
    by_name: dict[str, list[dict]] = {}
    for child in destination_children:
        by_name.setdefault(child["name"], []).append(child)

    for source in _list_children(service, source_id, source_resource_key):
        matches = by_name.get(source["name"], [])
        if source["mimeType"] == DRIVE_FOLDER_MIME:
            folders = [item for item in matches if item["mimeType"] == DRIVE_FOLDER_MIME]
            if len(folders) > 1:
                raise RuntimeError(f"Destination has duplicate folders named {source['name']!r}")
            if folders:
                target = folders[0]
            else:
                target = service.files().create(
                    body={"name": source["name"], "mimeType": DRIVE_FOLDER_MIME,
                          "parents": [destination_id]}, fields="id,name,mimeType").execute()
                counts["folders_created"] += 1
            nested = _copy_tree(service, source["id"], target["id"], source.get("resourceKey"))
            for key, value in nested.items():
                counts[key] += value
            continue

        files = [item for item in matches if item["mimeType"] != DRIVE_FOLDER_MIME]
        if len(files) > 1:
            raise RuntimeError(f"Destination has duplicate files named {source['name']!r}")
        if files:
            if not _same_blob(source, files[0]):
                raise RuntimeError(
                    f"Destination already contains a different file named {source['name']!r}; "
                    "rename or remove it before retrying the handoff")
            counts["files_already_present"] += 1
            continue
        if not source.get("capabilities", {}).get("canCopy", False):
            raise PermissionError(
                f"Viewer cannot copy {source['name']!r}. The owner must allow viewers to download/copy")
        request = service.files().copy(
            fileId=source["id"], body={"name": source["name"], "parents": [destination_id]},
            fields="id,name,mimeType,size,md5Checksum", supportsAllDrives=True)
        _execute(request, [(source["id"], source.get("resourceKey")),
                           (source_id, source_resource_key)])
        counts["files_copied"] += 1
    return counts


def clone_shared_folder_to_my_drive(source_url: str, destination_name: str = "LegalAI") -> dict:
    """Server-side copy a shared folder tree into the authenticated user's My Drive."""
    from google.colab import auth
    import google.auth
    from googleapiclient.discovery import build

    source_id, resource_key = parse_drive_folder_url(source_url)
    auth.authenticate_user()
    credentials, _ = google.auth.default()
    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    request = service.files().get(
        fileId=source_id, fields="id,name,mimeType,resourceKey,capabilities(canCopy)",
        supportsAllDrives=True)
    source = _execute(request, [(source_id, resource_key)])
    if source.get("mimeType") != DRIVE_FOLDER_MIME:
        raise ValueError("The shared source link does not point to a Drive folder")

    escaped = destination_name.replace("'", "\\'")
    response = service.files().list(
        q=(f"name = '{escaped}' and 'root' in parents and trashed = false and "
           f"mimeType = '{DRIVE_FOLDER_MIME}'"),
        fields="files(id,name,mimeType)", pageSize=10).execute()
    destinations = response.get("files", [])
    if len(destinations) > 1:
        raise RuntimeError(f"My Drive contains multiple folders named {destination_name!r}")
    if destinations:
        destination = destinations[0]
    else:
        destination = service.files().create(
            body={"name": destination_name, "mimeType": DRIVE_FOLDER_MIME,
                  "parents": ["root"]}, fields="id,name,mimeType").execute()
    if destination["id"] == source_id:
        raise ValueError("The source folder and destination folder are the same")
    counts = _copy_tree(service, source_id, destination["id"],
                        source.get("resourceKey") or resource_key)
    return {"source_id": source_id, "destination_id": destination["id"], **counts}


def ensure_legal_ai_folder(project: Path, required_filename: str,
                           shared_source_folder_url: str) -> None:
    """Keep normal mounted-Drive behavior, cloning only when required input is absent."""
    required = project / required_filename
    if required.is_file():
        print("Using existing Drive project:", project)
        return
    if not shared_source_folder_url.strip():
        raise FileNotFoundError(
            f"{required} is missing. Upload it normally or provide SHARED_SOURCE_FOLDER_URL")
    print("LegalAI training input is absent in this account; copying the shared project...")
    result = clone_shared_folder_to_my_drive(shared_source_folder_url, project.name)
    print("Shared project copy complete:", result)
    for _ in range(30):
        if required.is_file():
            print("Copied project is visible in mounted Drive:", project)
            return
        time.sleep(2)
    raise RuntimeError(
        "Drive finished the server-side copy but the mounted folder has not refreshed yet. "
        "Run all once more; the copied LegalAI folder will be reused without copying again.")
