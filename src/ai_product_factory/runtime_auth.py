from __future__ import annotations
import os
from dataclasses import dataclass
from enum import StrEnum

class AuthKind(StrEnum):
 OPENAI_API_KEY="openai_api_key"
 OPENAI_API_WIF="openai_api_wif"
 CODEX_WORKLOAD_IDENTITY="codex_workload_identity"
 NONE="none"

@dataclass(frozen=True)
class RuntimeAuth:
 kind:AuthKind;source:str;configured:bool

class RuntimeAuthResolver:
 """Reports configured auth capabilities without exposing credential values."""
 def __init__(self,environ:dict[str,str]|None=None)->None:self.environ=environ if environ is not None else os.environ
 def resolve_primary_api(self)->RuntimeAuth:
  if self.environ.get("OPENAI_API_WIF_PROVIDER_ID") and self.environ.get("OPENAI_API_WIF_SERVICE_ACCOUNT_ID"):
   return RuntimeAuth(AuthKind.OPENAI_API_WIF,"OpenAI API workload identity",True)
  if self.environ.get("OPENAI_API_KEY"):
   return RuntimeAuth(AuthKind.OPENAI_API_KEY,"OPENAI_API_KEY",True)
  return RuntimeAuth(AuthKind.NONE,"none",False)
 def resolve_codex(self)->RuntimeAuth:
  if self.environ.get("CODEX_WORKLOAD_IDENTITY_RULE_ID") and self.environ.get("CODEX_WORKLOAD_IDENTITY_TOKEN_FILE"):
   return RuntimeAuth(AuthKind.CODEX_WORKLOAD_IDENTITY,"Codex workload identity",True)
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
