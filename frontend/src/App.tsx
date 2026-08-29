import { useState } from "react";

function App() {
  const [question,setQuestion] = useState("");
  const [answer,setAnswer] = useState("");

  function sendQuestion(){
    setAnswer("这是一个模拟AI回答");
  }

  return (
    <div>
      <h1>DMU AI学习助手</h1>
      <input
        value={question}
        onChange={(event)=>setQuestion(event.target.value)}
        placeholder="请输入你的问题"
      />
      <button onClick={sendQuestion}>发送</button>
      <p>{answer}</p>
    </div>
  );
}

export default App;
