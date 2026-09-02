import { useState } from "react";

function App() {
  const [question, setQuestion] = useState("");
  const [loading,setLoading]=useState(false);
 type Message={
 role:string;
 content:string;
}


const [messages,setMessages]=useState<Message[]>([]);

 async function sendQuestion(){

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || loading) {
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/api/chat",
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json"
          },

          body: JSON.stringify({
            question: trimmedQuestion
          })
        }
      );

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data = await response.json();

      setMessages(prev => [
        ...prev,
        {
          role: "user",
          content: trimmedQuestion
        },
        {
          role: "ai",
          content: data.answer
        }
      ]);

      setQuestion("");
    } catch {
      setMessages(prev => [
        ...prev,
        {
          role: "ai",
          content: "AI服务暂时不可用，请稍后重试"
        }
      ]);
    } finally {
      setLoading(false);
    }
}

  return (
  <div className="app">

    <h1>
      DMU AI学习助手
    </h1>


    <div className="chat-box">

      {
        messages.map((message,index)=>(

          <div
          key={index}
          className={
            message.role==="user"
            ?
            "message user"
            :
            "message ai"
          }
          >

            {message.content}

          </div>

        ))
      }
      {
 loading && (
   <div className="message ai">
      AI正在思考...
   </div>
 )
}
      


    </div>


    <div className="input-area">

     <input
  value={question}
  onChange={(event)=>setQuestion(event.target.value)}
  placeholder="请输入你的问题"

  onKeyDown={(event)=>{

    if(event.key==="Enter"){

      sendQuestion();

    }

  }}
/>

      <button
      onClick={sendQuestion}
      disabled={loading}
      >
      {loading ? "思考中..." : "发送"}
      </button>


    </div>


  </div>
);
}

export default App;
