"""
多 AI 聊天室后端 —— WebSocket 长连接实现即时推送。

WebSocket vs HTTP 轮询：
- HTTP 每次都要重新建立连接，客户端只能反复「问有没有新消息」
- WebSocket 保持一条长连接，服务端有新消息立刻推给浏览器（像微信）
"""

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AsyncOpenAI
from starlette.middleware.base import BaseHTTPMiddleware

from prompts import ROLES

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("chatroom")

# 打印 OpenAI SDK 底层的 httpx 网络请求（URL、状态码、耗时）
for _net_logger in ("httpx", "httpcore"):
    logging.getLogger(_net_logger).setLevel(logging.DEBUG)

app = FastAPI(title="Matrix Digital Twin Chatroom")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        client = request.client.host if request.client else "unknown"
        logger.info(
            "HTTP 请求 → %s %s | client=%s",
            request.method,
            request.url.path,
            client,
        )
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "HTTP 响应 ← %s %s | status=%s | %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


app.add_middleware(RequestLogMiddleware)
client = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)
MODEL = os.getenv("MODEL", "gpt-4o-mini")
DEBATE_ROUNDS = int(os.getenv("DEBATE_ROUNDS", "3"))
HISTORY_LIMIT = 12


def format_history(messages: list[dict[str, str]]) -> str:
    if not messages:
        return "（尚无发言，你是第一个开口的）"
    lines = []
    for m in messages[-HISTORY_LIMIT:]:
        lines.append(f"[{m['speaker']}] {m['content']}")
    return "\n".join(lines)


def build_user_message(topic: str, role_name: str, history: list[dict[str, str]]) -> str:
    return f"""【辩论话题】{topic}
【你的身份】{role_name}
【最近对话记录】
{format_history(history)}

请严格保持你的人设，针对以上话题和对话，给出你的本轮发言。
不要重复他人已说过的观点，要推进辩论。"""


def _preview(text: str, limit: int = 120) -> str:
    one_line = text.replace("\n", " ").strip()
    if len(one_line) <= limit:
        return one_line
    return one_line[:limit] + "…"


async def call_ai(
    role_id: str,
    role_name: str,
    system_prompt: str,
    user_message: str,
    *,
    round_num: int,
    topic: str,
) -> str:
    logger.info(
        "大模型调用 → role=%s (%s) | round=%d | model=%s | topic=%s",
        role_id,
        role_name,
        round_num,
        MODEL,
        _preview(topic, 60),
    )
    logger.debug(
        "大模型请求详情 | system_len=%d | user_len=%d | user_preview=%s",
        len(system_prompt),
        len(user_message),
        _preview(user_message, 200),
    )

    start = time.perf_counter()
    try:
        response = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            temperature=0.85,
            max_tokens=500,
        )
        content = (response.choices[0].message.content or "").strip()
        elapsed_ms = (time.perf_counter() - start) * 1000
        usage = getattr(response, "usage", None)
        tokens = ""
        if usage:
            tokens = f" | tokens prompt={usage.prompt_tokens} completion={usage.completion_tokens}"

        logger.info(
            "大模型响应 ← role=%s (%s) | round=%d | %.1fms | len=%d%s | preview=%s",
            role_id,
            role_name,
            round_num,
            elapsed_ms,
            len(content),
            tokens,
            _preview(content, 150),
        )
        if role_id == "judge":
            logger.info("【毒舌评委发话】round=%d | %s", round_num, content)
        return content
    except Exception:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "大模型失败 ✗ role=%s (%s) | round=%d | %.1fms",
            role_id,
            role_name,
            round_num,
            elapsed_ms,
        )
        raise


async def send_json(ws: WebSocket, payload: dict[str, Any]) -> None:
    await ws.send_text(json.dumps(payload, ensure_ascii=False))


async def run_debate(ws: WebSocket, topic: str) -> None:
    logger.info("辩论开始 | topic=%s | rounds=%d", topic, DEBATE_ROUNDS)
    history: list[dict[str, str]] = []

    for round_num in range(1, DEBATE_ROUNDS + 1):
        logger.info("—— 第 %d 轮 ——", round_num)
        await send_json(ws, {"type": "status", "content": f"第 {round_num} 轮辩论开始…"})

        for role in ROLES:
            role_id = role["id"]
            role_name = role["name"]
            logger.info("角色发言调度 → %s (%s) | round=%d", role_id, role_name, round_num)

            await send_json(
                ws,
                {
                    "type": "typing",
                    "role": role_id,
                    "name": role_name,
                    "color": role["color"],
                },
            )

            if role_id == "judge":
                logger.info("【毒舌评委即将发言】round=%d", round_num)

            user_msg = build_user_message(topic, role_name, history)
            try:
                content = await call_ai(
                    role_id,
                    role_name,
                    role["system_prompt"],
                    user_msg,
                    round_num=round_num,
                    topic=topic,
                )
            except Exception as e:
                logger.error("辩论中断 | role=%s | round=%d | error=%s", role_id, round_num, e)
                await send_json(ws, {"type": "error", "content": f"AI 调用失败: {e}"})
                return

            history.append({"speaker": role_name, "content": content})
            logger.info(
                "推送消息 → role=%s | round=%d | preview=%s",
                role_id,
                round_num,
                _preview(content, 80),
            )
            await send_json(
                ws,
                {
                    "type": "message",
                    "role": role_id,
                    "name": role_name,
                    "color": role["color"],
                    "content": content,
                    "round": round_num,
                },
            )
            await asyncio.sleep(0.3)

    logger.info("辩论结束 | topic=%s", topic)
    await send_json(ws, {"type": "done", "content": "辩论结束，翘二郎腿欣赏完毕。"})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    client = ws.client.host if ws.client else "unknown"
    await ws.accept()
    logger.info("WebSocket 已连接 | client=%s", client)
    try:
        while True:
            raw = await ws.receive_text()
            logger.info("WebSocket 收请求 ← client=%s | raw=%s", client, raw)

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("WebSocket 无效 JSON | client=%s", client)
                await send_json(ws, {"type": "error", "content": "无效的 JSON 消息"})
                continue

            msg_type = data.get("type", "unknown")
            logger.info("WebSocket 解析 → type=%s | payload=%s", msg_type, data)

            if msg_type == "start_debate":
                topic = (data.get("topic") or "").strip()
                if not topic:
                    logger.warning("辩论请求被拒绝：话题为空")
                    await send_json(ws, {"type": "error", "content": "请输入辩论话题"})
                    continue
                if not os.getenv("OPENAI_API_KEY"):
                    logger.error("辩论请求被拒绝：未配置 OPENAI_API_KEY")
                    await send_json(
                        ws,
                        {"type": "error", "content": "请配置 OPENAI_API_KEY（见 .env.example）"},
                    )
                    continue
                logger.info("收到辩论话题 | topic=%s", topic)
                await send_json(ws, {"type": "status", "content": f"话题已接收：{topic}"})
                await run_debate(ws, topic)

            elif msg_type == "ping":
                logger.debug("WebSocket ping → pong")
                await send_json(ws, {"type": "pong"})

            else:
                logger.warning("未知 WebSocket 消息类型 | type=%s", msg_type)

    except WebSocketDisconnect:
        logger.info("WebSocket 已断开 | client=%s", client)
