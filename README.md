# DMU AI 学习助手

V0.1：React + TypeScript + Vite 前端调用 FastAPI 后端，页面显示 "DMU AI 学习助手"，并从后端获取 "Hello, DMU AI!"。

## 目录结构

```text
backend/    FastAPI 后端
frontend/   React 前端
```

## 环境要求

- Node.js（建议 18 以上）
- Python（建议 3.10 以上）

## 1. 启动后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

后端启动后访问 http://localhost:8000/api/hello，或打开 http://localhost:8000/docs 查看接口文档。

## 2. 启动前端

另开一个终端：

```powershell
cd frontend
npm install
npm run dev
```

浏览器打开 http://localhost:5173。

## 3. 测试

- 后端测试：浏览器访问 http://localhost:8000/api/hello，应返回 `{"message":"Hello, DMU AI!"}`。
- 前端测试：浏览器访问 http://localhost:5173，页面应显示 "DMU AI 学习助手" 和 "Hello, DMU AI!"。
