import json
import os
from collections.abc import Iterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel


# 读取 .env
load_dotenv()

# 获取 DeepSeek API Key
api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    raise RuntimeError(
        "DEEPSEEK_API_KEY 未配置，请检查 .env 文件"
    )


# 创建 DeepSeek 客户端
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com",
)


app = FastAPI(title="DMU AI 学习助手")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]


@app.get("/api/hello")
def hello() -> dict:
    return {"message": "Hello, DMU AI!"}


@app.post("/api/chat")
def chat(request: ChatRequest) -> StreamingResponse:

    deepseek_messages = [
        {
            "role": "system",
            "content": (
                "你是大连海事大学的 AI 学习助手。"
                "请用清晰、准确、适合大学生理解的方式回答问题。"
            ),
        }
    ]

    for message in request.messages:
        role = message.role

        if role == "ai":
            role = "assistant"

        deepseek_messages.append(
            {
                "role": role,
                "content": message.content,
            }
        )

    def generate() -> Iterator[str]:
        try:
            response = client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=deepseek_messages,
                stream=True,
            )

            for chunk in response:
                if not chunk.choices:
                    continue

                content = chunk.choices[0].delta.content

                if content:
                    yield (
                        "data: "
                        + json.dumps(
                            {"content": content},
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )

            yield "data: [DONE]\n\n"

        except Exception as exc:
            yield (
                "data: "
                + json.dumps(
                    {"error": f"DeepSeek API 调用失败: {exc}"},
                    ensure_ascii=False,
                )
                + "\n\n"
            )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
