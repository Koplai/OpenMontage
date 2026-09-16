"""HTTP client and task parsers for Kling official API providers."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from lib.provider_jobs import Deadline, atomic_write

from .errors import KlingAPIError, is_retryable_kling_error
from .schemas import (
    CLASSIC_FAILURE_STATUS,
    CLASSIC_PENDING_STATUSES,
    CLASSIC_SUCCESS_STATUS,
    DEFAULT_API_BASE_URL,
    TURBO_FAILURE_STATUS,
    TURBO_PENDING_STATUSES,
    TURBO_SUCCESS_STATUS,
)


class KlingClient:
    """Small synchronous client for the official Kling API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        session: Any | None = None,
        max_retries: int = 2,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("KLING_API_KEY")
        self.base_url = (base_url or os.environ.get("KLING_API_BASE_URL") or DEFAULT_API_BASE_URL).rstrip("/")
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.deadline: Deadline | None = None

    @property
    def headers(self) -> dict[str, str]:
        if not self.api_key:
            raise KlingAPIError(
                "KLING_API_KEY is not set. Configure KLING_API_KEY for official Kling API access.",
                http_status=401,
            )
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("post", path, json=payload)

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("get", path, params=params)

    def download(self, url: str, output_path: Path, timeout: int = 180) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = self.deadline or Deadline(timeout)
        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=deadline.remaining(timeout))
                self._raise_for_http_error(response)
                break
            except (requests.RequestException, KlingAPIError) as exc:
                if attempt == self.max_retries or (
                    isinstance(exc, KlingAPIError) and not is_retryable_kling_error(exc)
                ):
                    raise
                deadline.sleep(2.0 * (attempt + 1))
        content = getattr(response, "content", None)
        if content is None and hasattr(response, "iter_content"):
            content = b"".join(chunk for chunk in response.iter_content(chunk_size=1024 * 128) if chunk)
        deadline.remaining()
        if not content:
            raise ValueError("Kling returned empty media")
        atomic_write(output_path, content)
        return output_path

    def create_classic_task(self, path: str, payload: dict[str, Any]) -> str:
        data = self.post(path, payload)
        task_id = ((data.get("data") or {}).get("task_id"))
        if not task_id:
            raise KlingAPIError(f"Kling Classic create response missing data.task_id: {data}")
        return str(task_id)

    def poll_classic(
        self,
        path: str,
        task_id: str,
        result_key: str,
        timeout_seconds: int = 900,
        poll_interval: float = 5.0,
    ) -> list[dict[str, Any]]:
        self.deadline = self.deadline or Deadline(timeout_seconds)
        while True:
            self.deadline.remaining()
            data = self.get(f"{path.rstrip('/')}/{task_id}")
            payload = data.get("data") or {}
            status = payload.get("task_status") or payload.get("status")
            if status == CLASSIC_SUCCESS_STATUS:
                task_result = payload.get("task_result") or {}
                outputs = task_result.get(result_key) or []
                if not isinstance(outputs, list):
                    raise KlingAPIError(f"Kling Classic result path data.task_result.{result_key} is not a list")
                return outputs
            if status == CLASSIC_FAILURE_STATUS:
                message = payload.get("task_status_msg") or payload.get("message") or "Kling Classic task failed"
                raise KlingAPIError(str(message), code=payload.get("task_status"), response=data)
            if status not in CLASSIC_PENDING_STATUSES:
                raise KlingAPIError(f"Unexpected Kling Classic task status {status!r}", response=data)
            self.deadline.sleep(poll_interval)

    def create_turbo(self, path: str, payload: dict[str, Any]) -> str:
        data = self.post(path, payload)
        task_id = ((data.get("data") or {}).get("id"))
        if not task_id:
            raise KlingAPIError(f"Kling Turbo create response missing data.id: {data}")
        return str(task_id)

    def poll_turbo(
        self,
        task_id: str,
        timeout_seconds: int = 900,
        poll_interval: float = 5.0,
    ) -> list[dict[str, Any]]:
        self.deadline = self.deadline or Deadline(timeout_seconds)
        while True:
            self.deadline.remaining()
            data = self.get("/tasks", params={"task_ids": task_id})
            records = data.get("data") or []
            if not records:
                raise KlingAPIError(f"Kling Turbo poll response missing data[0]: {data}")
            record = records[0]
            status = record.get("status") or record.get("task_status")
            if status == TURBO_SUCCESS_STATUS:
                outputs = record.get("outputs") or []
                if not isinstance(outputs, list):
                    raise KlingAPIError("Kling Turbo result path data[0].outputs is not a list")
                return outputs
            if status == TURBO_FAILURE_STATUS:
                message = record.get("message") or record.get("error") or "Kling Turbo task failed"
                raise KlingAPIError(str(message), code=record.get("code"), request_id=record.get("request_id"), response=data)
            if status not in TURBO_PENDING_STATUSES:
                raise KlingAPIError(f"Unexpected Kling Turbo task status {status!r}", response=data)
            self.deadline.sleep(poll_interval)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = self._url(path)
        last_error: KlingAPIError | None = None
        # A read timeout/5xx can follow an accepted paid submission. Without a
        # documented idempotency guarantee, retrying that POST can bill twice.
        retries = self.max_retries if method.lower() == "get" else 0
        for attempt in range(retries + 1):
            try:
                timeout = self.deadline.remaining(30) if self.deadline else 30
                response = getattr(self.session, method)(url, headers=self.headers, timeout=timeout, **kwargs)
                self._raise_for_http_error(response)
                data = response.json()
                self._raise_for_business_error(data)
                return data
            except KlingAPIError as error:
                last_error = error
                if attempt >= retries or not is_retryable_kling_error(error):
                    raise
                self._backoff(attempt)
            except requests.RequestException as exc:
                last_error = KlingAPIError(str(exc))
                if attempt >= retries:
                    raise last_error from exc
                self._backoff(attempt)
        raise last_error or KlingAPIError("Kling API request failed")

    def _backoff(self, attempt: int) -> None:
        seconds = min(2.0 * (attempt + 1), 8.0)
        if self.deadline:
            self.deadline.sleep(seconds)
        else:
            time.sleep(seconds)

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    def _raise_for_http_error(self, response: Any) -> None:
        status = getattr(response, "status_code", None)
        if status is not None and 200 <= int(status) < 300:
            return
        code = None
        message = None
        request_id = None
        body: dict[str, Any] | None = None
        try:
            body = response.json()
            code = body.get("code")
            message = body.get("message") or body.get("msg")
            request_id = body.get("request_id") or body.get("requestId")
        except Exception:
            text = getattr(response, "text", "")
            message = text[:500] if text else f"HTTP {status}"
        raise self._format_error(
            code=code,
            message=message or f"HTTP {status}",
            request_id=request_id,
            http_status=int(status) if status is not None else None,
            response=body,
        )

    def _raise_for_business_error(self, data: dict[str, Any]) -> None:
        code = data.get("code")
        if code in (None, 0, "0"):
            return
        raise self._format_error(
            code=code,
            message=str(data.get("message") or data.get("msg") or "Kling API returned an error"),
            request_id=data.get("request_id") or data.get("requestId"),
            response=data,
        )

    @staticmethod
    def _format_error(
        *,
        code: str | int | None,
        message: str,
        request_id: str | None = None,
        http_status: int | None = None,
        response: dict[str, Any] | None = None,
    ) -> KlingAPIError:
        if str(code) == "1303" and "并发/资源包限制" not in message:
            message = f"{message} (并发/资源包限制: parallel task over resource pack limit)"
        return KlingAPIError(
            message=message,
            code=code,
            request_id=request_id,
            http_status=http_status,
            response=response,
        )
