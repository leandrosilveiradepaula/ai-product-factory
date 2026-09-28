from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


class SupabaseManagementError(RuntimeError):
    pass


@dataclass(frozen=True)
class SupabaseProjectBinding:
    project_ref: str
    access_token: str
    permission_mode: str = "read"

    def __post_init__(self) -> None:
        if not self.project_ref.strip():
            raise ValueError("project_ref is required")
        if not self.access_token.strip():
            raise ValueError("access_token is required")
        if self.permission_mode not in {"read", "read_write"}:
            raise ValueError("permission_mode must be read or read_write")


class SupabaseManagementClient:
    def __init__(
        self,
        binding: SupabaseProjectBinding,
        *,
        base_url: str = "https://api.supabase.com",
        transport: Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]] | None = None,
    ) -> None:
        self.binding=binding
        self.base_url=base_url.rstrip("/")
        self.transport=transport or self._urlopen

    def _urlopen(self, method: str, url: str, headers: dict[str,str], body: bytes | None) -> tuple[int,bytes]:
        request=urllib.request.Request(url,data=body,method=method,headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=30) as response:
                return int(response.status),response.read()
        except urllib.error.HTTPError as exc:
            raise SupabaseManagementError(f"Supabase Management API HTTP {exc.code}") from exc

    def _request(self, method: str, path: str, payload: dict[str,Any] | None = None) -> Any:
        headers={
            "Authorization":f"Bearer {self.binding.access_token}",
            "Accept":"application/json",
        }
        body=None
        if payload is not None:
            headers["Content-Type"]="application/json"
            body=json.dumps(payload,separators=(",",":")).encode()
        status,raw=self.transport(method,f"{self.base_url}{path}",headers,body)
        if status < 200 or status >= 300:
            raise SupabaseManagementError(f"Supabase Management API HTTP {status}")
        return json.loads(raw.decode() or "null")

    def project(self) -> dict[str,Any]:
        return self._request("GET",f"/v1/projects/{self.binding.project_ref}")

    def read_only_query(self, sql: str) -> Any:
        statement=sql.strip()
        if not statement:
            raise ValueError("sql is required")
        return self._request(
            "POST",
            f"/v1/projects/{self.binding.project_ref}/database/query/read-only",
            {"query":statement},
        )

    def write_query(self, sql: str, *, approved: bool = False) -> Any:
        if self.binding.permission_mode != "read_write":
            raise PermissionError("binding is not authorized for database writes")
        if not approved:
            raise PermissionError("database write requires an explicit approved operation")
        statement=sql.strip()
        if not statement:
            raise ValueError("sql is required")
        return self._request(
            "POST",
            f"/v1/projects/{self.binding.project_ref}/database/query",
            {"query":statement},
        )


@dataclass(frozen=True)
class SupabaseProvisionRequest:
    name: str
    organization_slug: str
    region_group: str = "americas"
    desired_instance_size: str | None = None

    def payload(self, db_password: str) -> dict[str,Any]:
        if not self.name.strip() or not self.organization_slug.strip() or not db_password.strip():
            raise ValueError("name, organization_slug and db_password are required")
        payload:dict[str,Any]={
            "name":self.name,
            "organization_slug":self.organization_slug,
            "db_pass":db_password,
            "region_selection":{"type":"smartGroup","code":self.region_group},
        }
        if self.desired_instance_size:
            payload["desired_instance_size"]=self.desired_instance_size
        return payload


def create_project(
    access_token: str,
    request: SupabaseProvisionRequest,
    db_password: str,
    *,
    approved_cost: bool = False,
    transport: Callable[[str,str,dict[str,str],bytes|None],tuple[int,bytes]] | None = None,
) -> Any:
    if not approved_cost:
        raise PermissionError("Supabase project creation requires explicit human cost approval")
    binding=SupabaseProjectBinding(project_ref="provisioning",access_token=access_token,permission_mode="read_write")
    client=SupabaseManagementClient(binding,transport=transport)
    return client._request("POST","/v1/projects",request.payload(db_password))
