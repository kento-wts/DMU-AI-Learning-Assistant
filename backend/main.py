from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="DMU AI 学习助手")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str


@app.get("/api/hello")
def hello() -> dict:
    return {"message": "Hello, DMU AI!"}


import time


@app.post("/api/chat")
def chat(request: ChatRequest):

    time.sleep(3)

    return {
        "answer":f"你的问题是：{request.question}这是AI模拟回答"
    }
