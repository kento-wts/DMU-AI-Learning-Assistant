import { useEffect, useState } from "react";

const API_URL = "http://localhost:8000/api/hello";

function App() {
  const [message, setMessage] = useState("正在连接后端...");

  useEffect(() => {
    fetch(API_URL)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((data: { message: string }) => {
        setMessage(data.message);
      })
      .catch(() => {
        setMessage("无法连接后端，请先启动后端服务");
      });
  }, []);

  return (
    <main className="page">
      <h1>DMU AI 学习助手</h1>
      <p className="backend-message">{message}</p>
    </main>
  );
}

export default App;
