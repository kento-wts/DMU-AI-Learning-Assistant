import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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


class ChatRequest(BaseModel):
    question: str


@app.get("/api/hello")
def hello() -> dict:
    return {"message": "Hello, DMU AI!"}


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict:

    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是大连海事大学的 AI 学习助手。"
                        "请用清晰、准确、适合大学生理解的方式回答问题。"
                    ),
                },
                {
                    "role": "user",
                    "content": request.question,
                },
            ],
            stream=False,
        )

        answer = response.choices[0].message.content

        return {
            "answer": answer or ""
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"DeepSeek API 调用失败: {exc}",
        )