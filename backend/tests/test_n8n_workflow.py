import json
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / "automation/n8n/document_intake.json"


def test_workflow_connections_reference_existing_nodes():
    wf = json.loads(WORKFLOW.read_text())
    names = {n["name"] for n in wf["nodes"]}
    assert len(names) == len(wf["nodes"])
    for src, outputs in wf["connections"].items():
        assert src in names
        for branch in outputs["main"]:
            for link in branch:
                assert link["node"] in names


def test_workflow_hits_real_api_routes():
    text = WORKFLOW.read_text()
    for route in ("/auth/login", "/documents/upload", "/status"):
        assert route in text
