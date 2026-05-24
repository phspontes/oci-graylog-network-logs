#!/usr/bin/env python3
"""Pull archived OCI logs from Object Storage and send them to Graylog GELF HTTP.

Designed for OCI Logging -> Service Connector Hub -> Object Storage archives.
Authentication uses Instance Principal by default.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib import error, request

try:
    import oci
except ImportError as exc:
    raise SystemExit("Missing dependency: install with `python3 -m pip install oci`") from exc

UTC = dt.timezone.utc
STOP = False


def _handle_signal(signum: int, frame: object) -> None:
    global STOP
    STOP = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OCI Object Storage archived logs to Graylog GELF HTTP shipper")
    parser.add_argument("--region", default=os.getenv("OCI_REGION"), help="OCI region, e.g. sa-vinhedo-1")
    parser.add_argument("--namespace", default=os.getenv("OCI_OS_NAMESPACE"), help="Object Storage namespace. If omitted, the script discovers it.")
    parser.add_argument("--bucket", default=os.getenv("OCI_LOG_BUCKET"), required=not os.getenv("OCI_LOG_BUCKET"), help="Object Storage bucket name")
    parser.add_argument("--prefix", default=os.getenv("OCI_LOG_PREFIX", ""), help="Object prefix to scan")
    parser.add_argument("--graylog-url", default=os.getenv("GRAYLOG_GELF_HTTP_URL", "http://127.0.0.1:12202/gelf"), help="Graylog GELF HTTP input URL")
    parser.add_argument("--state-file", default=os.getenv("OCI_OS_LOG_STATE_FILE", "/var/lib/oci-object-logs-to-graylog/state.json"), help="Checkpoint state file")
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("OCI_OS_LOG_INTERVAL_SECONDS", "300")), help="Polling interval")
    parser.add_argument("--max-objects", type=int, default=int(os.getenv("OCI_OS_LOG_MAX_OBJECTS", "100")), help="Maximum new objects to process per cycle")
    parser.add_argument("--list-limit", type=int, default=int(os.getenv("OCI_OS_LOG_LIST_LIMIT", "1000")), help="Object list page size")
    parser.add_argument("--once", action="store_true", help="Run one polling cycle and exit")
    parser.add_argument("--dry-run", action="store_true", help="Print GELF payloads instead of sending")
    parser.add_argument("--include-processed", action="store_true", help="Ignore checkpoint and reprocess listed objects")
    parser.add_argument("--skip-graylog-input-ensure", action="store_true", help="Do not create/check the Graylog GELF HTTP input before shipping")
    parser.add_argument("--graylog-api-url", default=os.getenv("GRAYLOG_API_URL", "http://127.0.0.1:9000/api"), help="Graylog API URL")
    parser.add_argument("--graylog-user", default=os.getenv("GRAYLOG_USER", "admin"), help="Graylog admin user")
    parser.add_argument("--graylog-password", default=os.getenv("GRAYLOG_PASSWORD"), help="Graylog admin password. Defaults to OCI instance OCID from metadata.")
    parser.add_argument("--graylog-input-title", default=os.getenv("GRAYLOG_INPUT_TITLE", "OCI Object Storage Logs"), help="Graylog input title")
    parser.add_argument("--graylog-input-port", type=int, default=int(os.getenv("GRAYLOG_INPUT_PORT", "12202")), help="Graylog GELF HTTP input port")
    return parser.parse_args()


def now_utc() -> dt.datetime:
    return dt.datetime.now(tz=UTC)


def parse_time(value: Any) -> Optional[dt.datetime]:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        try:
            parsed = dt.datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"processed": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if "processed" not in data or not isinstance(data["processed"], dict):
            data["processed"] = {}
        return data
    except Exception:
        return {"processed": {}}


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def object_marker(obj: Any) -> str:
    etag = getattr(obj, "etag", None) or ""
    size = getattr(obj, "size", None) or ""
    modified = getattr(obj, "time_modified", None) or ""
    return f"{etag}:{size}:{modified}"


def is_processed(state: Dict[str, Any], obj: Any) -> bool:
    return state.get("processed", {}).get(obj.name) == object_marker(obj)


def mark_processed(state: Dict[str, Any], obj: Any) -> None:
    state.setdefault("processed", {})[obj.name] = object_marker(obj)
    state["updated_at"] = now_utc().isoformat()


def prune_state(state: Dict[str, Any], keep_last: int = 20000) -> None:
    processed = state.get("processed", {})
    if len(processed) <= keep_last:
        return
    keys = sorted(processed.keys())[-keep_last:]
    state["processed"] = {key: processed[key] for key in keys}


def list_objects(client: Any, namespace: str, bucket: str, prefix: str, limit: int) -> Iterable[Any]:
    start = None
    while True:
        response = client.list_objects(
            namespace_name=namespace,
            bucket_name=bucket,
            prefix=prefix or None,
            fields="name,size,etag,timeModified",
            limit=limit,
            start=start,
        )
        for obj in response.data.objects:
            yield obj
        start = response.data.next_start_with
        if not start:
            break


def read_object_bytes(client: Any, namespace: str, bucket: str, name: str) -> bytes:
    response = client.get_object(namespace, bucket, name)
    return response.data.content


def decode_payload(name: str, payload: bytes) -> str:
    if name.endswith(".gz") or payload[:2] == b"\x1f\x8b":
        return gzip.GzipFile(fileobj=io.BytesIO(payload)).read().decode("utf-8", "replace")
    return payload.decode("utf-8", "replace")


def iter_json_values(value: Any) -> Iterable[Any]:
    if isinstance(value, list):
        for item in value:
            yield from iter_json_values(item)
        return
    if isinstance(value, dict):
        for key in ("data", "records", "items", "logs", "results"):
            child = value.get(key)
            if isinstance(child, list):
                for item in child:
                    yield from iter_json_values(item)
                return
        yield value
        return
    yield value


def parse_log_records(text: str) -> Iterable[Dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return
    try:
        parsed = json.loads(stripped)
        for item in iter_json_values(parsed):
            if isinstance(item, dict):
                yield item
            else:
                yield {"message": str(item)}
        return
    except json.JSONDecodeError:
        pass

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                yield parsed
            else:
                yield {"message": str(parsed)}
        except json.JSONDecodeError:
            yield {"message": line}


def nested_get(data: Dict[str, Any], path: List[str]) -> Any:
    current: Any = data
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def record_time(record: Dict[str, Any]) -> dt.datetime:
    candidates = [
        record.get("time"),
        record.get("datetime"),
        record.get("eventTime"),
        nested_get(record, ["data", "time"]),
        nested_get(record, ["data", "datetime"]),
        nested_get(record, ["data", "eventTime"]),
        nested_get(record, ["data", "logContent", "time"]),
    ]
    for candidate in candidates:
        parsed = parse_time(candidate)
        if parsed:
            return parsed
    return now_utc()


def record_id(record: Dict[str, Any], object_name: str, index: int) -> str:
    for key in ("id", "eventId", "oracle.logid", "logId"):
        value = record.get(key) or nested_get(record, ["data", key])
        if value:
            return str(value)
    raw = json.dumps(record, sort_keys=True, default=str)
    return hashlib.sha256(f"{object_name}:{index}:{raw}".encode("utf-8")).hexdigest()


def map_level(value: Any) -> int:
    if value is None:
        return 6
    text = str(value).lower()
    if text in {"fatal", "critical", "crit"}:
        return 2
    if text in {"error", "err"}:
        return 3
    if text in {"warn", "warning"}:
        return 4
    if text == "notice":
        return 5
    if text in {"debug", "trace"}:
        return 7
    return 6


def make_gelf(record: Dict[str, Any], object_name: str, index: int) -> Dict[str, Any]:
    data = record.get("data") if isinstance(record.get("data"), dict) else record
    log_content = data.get("logContent") if isinstance(data.get("logContent"), dict) else {}
    log_content_data = log_content.get("data") if isinstance(log_content.get("data"), dict) else {}
    message = (
        log_content_data.get("message")
        or data.get("message")
        or record.get("message")
        or json.dumps(record, default=str, ensure_ascii=False)
    )
    ts = record_time(record)
    gelf = {
        "version": "1.1",
        "host": str(data.get("source") or data.get("resourceName") or "oci-object-storage"),
        "short_message": str(message)[:32000],
        "timestamp": ts.timestamp(),
        "level": map_level(data.get("level") or data.get("severity")),
        "_oci_event_id": record_id(record, object_name, index),
        "_oci_object_name": object_name,
        "_oci_compartment_id": data.get("compartmentId"),
        "_oci_log_group_id": data.get("logGroupId"),
        "_oci_log_id": data.get("logId"),
        "_oci_source": data.get("source"),
        "_oci_type": data.get("type"),
        "_oci_raw": json.dumps(record, default=str, ensure_ascii=False),
    }
    return {key: value for key, value in gelf.items() if value is not None}


def post_gelf(url: str, payload: Dict[str, Any], dry_run: bool) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if dry_run:
        print(body.decode("utf-8"))
        return
    req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=20) as resp:
            if resp.status >= 300:
                raise RuntimeError(f"Graylog returned HTTP {resp.status}")
    except error.HTTPError as exc:
        raise RuntimeError(f"Graylog HTTP error {exc.code}: {exc.read().decode('utf-8', 'ignore')}") from exc


def get_instance_ocid() -> str:
    req = request.Request(
        "http://169.254.169.254/opc/v2/instance/id",
        headers={"Authorization": "Bearer Oracle"},
        method="GET",
    )
    with request.urlopen(req, timeout=10) as resp:
        return resp.read().decode("utf-8").strip()


def graylog_request(api_url: str, user: str, password: str, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Any:
    url = api_url.rstrip("/") + path
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": f"Basic {token}",
        "X-Requested-By": "oci-object-storage-logs-to-graylog",
        "Accept": "application/json",
    }
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", "replace")
        if not body:
            return None
        return json.loads(body)


def wait_for_graylog_api(api_url: str, user: str, password: str, timeout_seconds: int = 900) -> None:
    deadline = time.time() + timeout_seconds
    last_error = None
    while time.time() < deadline:
        try:
            graylog_request(api_url, user, password, "GET", "/system/cluster/nodes")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(10)
    raise RuntimeError(f"Graylog API did not become ready: {last_error}")


def first_graylog_node_id(api_url: str, user: str, password: str) -> str:
    data = graylog_request(api_url, user, password, "GET", "/system/cluster/nodes")
    nodes = data.get("nodes", []) if isinstance(data, dict) else []
    if isinstance(nodes, dict) and nodes:
        return next(iter(nodes.keys()))
    if isinstance(nodes, list) and nodes:
        node_id = nodes[0].get("node_id") or nodes[0].get("id")
        if node_id:
            return node_id
    raise RuntimeError("No Graylog node found through /system/cluster/nodes")


def graylog_input_exists(api_url: str, user: str, password: str, title: str, port: int) -> bool:
    data = graylog_request(api_url, user, password, "GET", "/system/inputs")
    inputs = data.get("inputs", []) if isinstance(data, dict) else []
    for item in inputs:
        input_obj = item.get("message_input") if isinstance(item.get("message_input"), dict) else item
        config = input_obj.get("configuration", {}) if isinstance(input_obj, dict) else {}
        if input_obj.get("title") == title or int(config.get("port", -1)) == port:
            return True
    return False


def ensure_graylog_gelf_http_input(api_url: str, user: str, password: str, title: str, port: int) -> None:
    print(f"Ensuring Graylog GELF HTTP input title={title!r} port={port}", flush=True)
    wait_for_graylog_api(api_url, user, password)
    if graylog_input_exists(api_url, user, password, title, port):
        print("Graylog input already exists", flush=True)
        return
    node_id = first_graylog_node_id(api_url, user, password)
    payload = {
        "title": title,
        "type": "org.graylog2.inputs.gelf.http.GELFHttpInput",
        "global": False,
        "node": node_id,
        "configuration": {
            "bind_address": "0.0.0.0",
            "port": port,
            "recv_buffer_size": 1048576,
            "max_message_size": 2097152,
            "tls_enable": False,
            "tls_cert_file": "",
            "tls_key_file": "",
            "tls_key_password": "",
            "tls_client_auth": "disabled",
            "tls_client_auth_cert_file": "",
            "decompress_size_limit": 8388608,
            "override_source": None,
        },
    }
    graylog_request(api_url, user, password, "POST", "/system/inputs", payload)
    print("Graylog input created", flush=True)


def process_object(client: Any, namespace: str, bucket: str, obj: Any, graylog_url: str, dry_run: bool) -> int:
    payload = read_object_bytes(client, namespace, bucket, obj.name)
    text = decode_payload(obj.name, payload)
    sent = 0
    for index, record in enumerate(parse_log_records(text)):
        post_gelf(graylog_url, make_gelf(record, obj.name, index), dry_run)
        sent += 1
    return sent


def main() -> int:
    args = parse_args()
    signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
    config = {"region": args.region or signer.region}
    client = oci.object_storage.ObjectStorageClient(config=config, signer=signer)
    namespace = args.namespace or client.get_namespace().data
    state_path = Path(args.state_file)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if not args.skip_graylog_input_ensure and not args.dry_run:
        graylog_password = args.graylog_password or get_instance_ocid()
        ensure_graylog_gelf_http_input(
            args.graylog_api_url,
            args.graylog_user,
            graylog_password,
            args.graylog_input_title,
            args.graylog_input_port,
        )

    while not STOP:
        state = load_state(state_path)
        objects = sorted(
            list_objects(client, namespace, args.bucket, args.prefix, args.list_limit),
            key=lambda item: (item.time_modified or dt.datetime.min.replace(tzinfo=UTC), item.name),
        )
        candidates = [obj for obj in objects if args.include_processed or not is_processed(state, obj)]
        candidates = candidates[: args.max_objects]
        total_events = 0

        print(f"Found {len(candidates)} new object(s) in bucket={args.bucket} prefix={args.prefix!r}", flush=True)
        for obj in candidates:
            print(f"Processing object: {obj.name}", flush=True)
            sent = process_object(client, namespace, args.bucket, obj, args.graylog_url, args.dry_run)
            total_events += sent
            if not args.dry_run:
                mark_processed(state, obj)
                prune_state(state)
                save_state(state_path, state)
            print(f"Processed object: {obj.name}; events={sent}", flush=True)

        print(f"Cycle complete. events={total_events}", flush=True)
        if args.once:
            break
        for _ in range(args.interval_seconds):
            if STOP:
                break
            time.sleep(1)

    return 0


if __name__ == "__main__":
    sys.exit(main())
