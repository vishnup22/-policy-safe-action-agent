"""Validate every JSON example in the frozen document, expanding its explicit placeholders."""

import copy
import json
import re
from pathlib import Path
from typing import Any

from psa.api import models as m
from psa.domain import ActionIntent, Decision, Event

ROOT = Path(__file__).resolve().parents[2]


def test_every_document_example() -> None:
    document = (ROOT / "docs/contracts/api.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\s*\n(.*?)```", document, re.S)
    examples: list[Any] = []
    decoder = json.JSONDecoder()
    for block in blocks:
        clean = re.sub(r"/\*.*?\*/|//[^\n]*", "", block, flags=re.S).strip()
        while clean:
            value, end = decoder.raw_decode(clean)
            examples.append(value)
            clean = clean[end:].strip()
    models = [
        m.LoginRequest,
        m.LoginResponse,
        m.ConversationRequest,
        m.ConversationCreated,
        m.Conversations,
        m.MessageRequest,
        m.MessageResponse,
        m.EventsResponse,
        Event,
        ActionIntent,
        Decision,
        m.Approvals,
        m.ResolveRequest,
        m.Policies,
        m.PolicyDetail,
        m.PolicyDiff,
        m.Runs,
        m.Health,
    ]
    assert len(examples) == len(models) == 18
    intent = examples[9]
    decision = copy.deepcopy(examples[10])
    decision["outcome"] = "REQUIRE_APPROVAL"
    approval = examples[11]["items"][0]
    approval["intent"] = intent
    approval["decision"] = decision
    for value, model in zip(examples, models, strict=True):
        if model is m.Conversations:
            for status in value["items"][0]["status"].split(" | "):
                variant = copy.deepcopy(value)
                variant["items"][0]["status"] = status
                model.model_validate(variant)
        elif model is m.ResolveRequest:
            for resolution in value["resolution"].split(" | "):
                model.model_validate({**value, "resolution": resolution})
        else:
            model.model_validate(value)
