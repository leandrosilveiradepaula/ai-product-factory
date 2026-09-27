from __future__ import annotations
import os
from dataclasses import dataclass
from enum import StrEnum

class AuthKind(StrEnum):
 OPENAI_API_KEY="openai_api_key"
 OPENAI_API_WIF="openai_api_wif"
 CODEX_WORKLOAD_IDENTITY="codex_workload_identity"
 CODEX_ACCESS_TOKEN="codex_access_token"
 NONE="none"

@dataclass(frozen=True)
class RuntimeAuth:
 kind:AuthKind;source:str;configured:bool

class RuntimeAuthResolver:
 """Reports configured auth capabilities without exposing credential values."""
 def __init__(self,environ:dict[str,str]|None=None)->None:self.environ=environ if environ is not None else os.environ

 def resolve_primary_api(self)->RuntimeAuth:
  wif_values=(
   self.environ.get("OPENAI_IDENTITY_PROVIDER_ID"),
   self.environ.get("OPENAI_SERVICE_ACCOUNT_ID"),
   self.environ.get("OPENAI_WIF_AUDIENCE"),
  )
  if any(wif_values):
   if all(wif_values):
    return RuntimeAuth(AuthKind.OPENAI_API_WIF,"OpenAI API workload identity",True)
   return RuntimeAuth(AuthKind.NONE,"incomplete OpenAI API workload identity",False)
  if self.environ.get("OPENAI_API_KEY"):
   return RuntimeAuth(AuthKind.OPENAI_API_KEY,"OPENAI_API_KEY",True)
  return RuntimeAuth(AuthKind.NONE,"none",False)

 def resolve_codex(self)->RuntimeAuth:
  rule=self.environ.get("OPENAI_FEDERATION_RULE_ID")
  token_file=self.environ.get("OPENAI_IDENTITY_TOKEN_FILE")
  if rule or token_file:
   if rule and token_file:
    return RuntimeAuth(AuthKind.CODEX_WORKLOAD_IDENTITY,"Codex workload identity",True)
   return RuntimeAuth(AuthKind.NONE,"incomplete Codex workload identity",False)
  if self.environ.get("CODEX_ACCESS_TOKEN"):
   return RuntimeAuth(AuthKind.CODEX_ACCESS_TOKEN,"CODEX_ACCESS_TOKEN",True)
  return RuntimeAuth(AuthKind.NONE,"none",False)

 def resolve(self)->RuntimeAuth:
  primary=self.resolve_primary_api()
  if primary.configured:return primary
  return self.resolve_codex()

 def available_kinds(self)->tuple[AuthKind,...]:
  kinds=[]
  for auth in (self.resolve_primary_api(),self.resolve_codex()):
   if auth.configured:kinds.append(auth.kind)
  return tuple(kinds)
