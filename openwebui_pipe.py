from pydantic import BaseModel, Field
from fastapi import Request
import json, re
import requests

from open_webui.models.users import Users
from open_webui.utils.chat import generate_chat_completion


class Pipe:
    class Valves(BaseModel):
        BASE_MODEL: str = Field(
            default="dolphin3:8b", description="日本語→英語プロンプト生成に使うモデル"
        )
        BRIDGE_ENQUEUE_URL: str = Field(
            default="http://localhost:8000/enqueue", description="bridge /enqueue"
        )
        ALWAYS_NEGATIVE: str = Field(default="", description="常に足すネガティブ(任意)")
        TIMEOUT_S: int = Field(default=120, description="HTTPタイムアウト")

    def __init__(self):
        self.valves = self.Valves()

    def pipes(self):
        return [{"id": "jp2comfy_enqueue", "name": "JP→ComfyUI enqueue (no image)"}]

    async def pipe(self, body: dict, __user__: dict, __request__: Request):
        user = Users.get_user_by_id(__user__["id"])

        # 最新のユーザー発話を取得
        user_text = ""
        for m in reversed(body.get("messages", [])):
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break

        user_text = (user_text or "").strip()
        if not user_text:
            return "(skip) empty user message"

        # 1) ベースLLMに「strict JSON」だけを返させる（tool不要）
        sys = (
            "You are a prompt engineer for ComfyUI/Stable Diffusion.\n"
            "Return STRICT JSON only (no markdown, no commentary).\n"
            'Schema: {"positive":"...","negative":"..."}\n'
            "positive: English prompt. negative: optional English negative prompt."
        )
        usr = f"Japanese instruction:\n{user_text}\n\nReturn JSON only:"

        sub_body = {
            "model": self.valves.BASE_MODEL,
            "messages": [
                {"role": "system", "content": sys},
                {"role": "user", "content": usr},
            ],
            "stream": False,
            "temperature": 0.7,
            "max_tokens": 300,
        }

        resp = await generate_chat_completion(__request__, sub_body, user)
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")

        # JSON抽出（モデルが余計な文字を混ぜても耐える）
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            return f"[ERROR] prompt JSON parse failed. Raw:\n{content}"

        j = json.loads(m.group(0))
        positive = (j.get("positive") or "").strip()
        negative = (j.get("negative") or "").strip()

        if self.valves.ALWAYS_NEGATIVE:
            negative = (self.valves.ALWAYS_NEGATIVE + " " + negative).strip()

        # 2) bridgeへ投げる（待たない）
        r = requests.post(
            self.valves.BRIDGE_ENQUEUE_URL,
            json={"prompt": positive, "negative": negative or None},
            timeout=self.valves.TIMEOUT_S,
        )
        r.raise_for_status()
        data = r.json()
        prompt_id = data.get("prompt_id", "")

        # 3) チャットには「投入した」ことだけ返す（画像表示しない）
        return (
            f"Queued to ComfyUI.\n"
            f"prompt_id: {prompt_id}\n"
            f"positive: {positive}\n"
            f"negative: {negative}"
        )

