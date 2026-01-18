import json, uuid, time
import requests
import websocket
from fastapi import FastAPI
from pydantic import BaseModel

import hashlib

def sha10(s: str | None) -> str:
    s = s or ""
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


COMFY = "http://localhost:8188"
WORKFLOW_PATH = "./workflow_api.json"

POS_VALUE_NODE = "26:24"  # positive本体
NEG_VALUE_NODE = "25:24"  # negative本体

app = FastAPI(title="ComfyUI Bridge")

class GenReq(BaseModel):
    prompt: str
    negative: str | None = None

def load_workflow():
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def patch_prompt(workflow: dict, positive: str, negative: str | None):
    workflow[POS_VALUE_NODE]["inputs"]["value"] = positive
    if negative is not None:
        workflow[NEG_VALUE_NODE]["inputs"]["value"] = negative

def queue_prompt(workflow: dict, client_id: str):
    r = requests.post(f"{COMFY}/prompt", json={"prompt": workflow, "client_id": client_id}, timeout=30)
    r.raise_for_status()
    return r.json()["prompt_id"]

def wait_done_ws(client_id: str, timeout_s: int = 300):
    ws = websocket.WebSocket()
    ws.connect(f"{COMFY.replace('http://','ws://')}/ws?clientId={client_id}")
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        msg = ws.recv()
        if not msg:
            continue
        data = json.loads(msg)
        if data.get("type") == "executing" and data.get("data", {}).get("node") is None:
            break
    ws.close()

def get_first_image_url(prompt_id: str):
    h = requests.get(f"{COMFY}/history/{prompt_id}", timeout=30)
    h.raise_for_status()
    hist = h.json().get(prompt_id, {})
    outputs = hist.get("outputs", {})
    for node_out in outputs.values():
        images = node_out.get("images")
        if images:
            img = images[0]
            filename = img["filename"]
            subfolder = img.get("subfolder", "")
            img_type = img.get("type", "output")
            return f"{COMFY}/view?filename={filename}&subfolder={subfolder}&type={img_type}"
    raise RuntimeError("historyに画像が見つからない。SaveImageノードがあるか確認。")

@app.post("/generate")
def generate(req: GenReq):
    wf = load_workflow()
    patch_prompt(wf, req.prompt, req.negative)
    client_id = str(uuid.uuid4())
    prompt_id = queue_prompt(wf, client_id)
    wait_done_ws(client_id)
    url = get_first_image_url(prompt_id)
    return {"prompt_id": prompt_id, "image_url": url}

@app.post("/enqueue")
def enqueue(req: GenReq):
    if not (req.prompt or "").strip():
        print("[ENQUEUE-SKIP] empty prompt")
        return {"prompt_id": "(skipped-empty)"}

    print(
        "[ENQUEUE-IN ] "
        f"pos_sha={sha10(req.prompt)} neg_sha={sha10(req.negative)} "
        f"pos_head={req.prompt[:60]!r}"
    )

    wf = load_workflow()
    patch_prompt(wf, req.prompt, req.negative)
    client_id = str(uuid.uuid4())
    prompt_id = queue_prompt(wf, client_id)

    print(
        "[ENQUEUE-OUT] "
        f"prompt_id={prompt_id} client_id={client_id} "
        f"pos_sha={sha10(req.prompt)}"
    )

    return {"prompt_id": prompt_id}

