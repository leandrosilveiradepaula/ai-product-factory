from __future__ import annotations

import re
from collections.abc import Mapping


_VALUE=re.compile(r"^[A-Za-z0-9_.:/@+-]{1,160}$")
_SHA256=re.compile(r"^[0-9a-f]{64}$")


def _value(name:str,value:str)->str:
    text=str(value).strip()
    if "\n" in text or "\r" in text or not _VALUE.fullmatch(text):
        raise ValueError(f"invalid provenance trailer value: {name}")
    return text


def provenance_commit_message(subject:str,trailers:Mapping[str,str])->str:
    title=" ".join(str(subject).strip().splitlines()).strip()
    if not title:
        raise ValueError("commit subject is required")
    lines=[]
    for name,value in trailers.items():
        if not re.fullmatch(r"Factory-[A-Za-z0-9-]+",name):
            raise ValueError("invalid provenance trailer name")
        text=_value(name,value)
        if name=="Factory-Context-SHA256" and not _SHA256.fullmatch(text):
            raise ValueError("Factory-Context-SHA256 must be a 64-character lowercase hex hash")
        lines.append(f"{name}: {text}")
    if not lines:
        raise ValueError("at least one provenance trailer is required")
    return title+"\n\n"+"\n".join(lines)
