import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function App() {
  const [question, setQuestion] = useState("");
  const [loading,setLoading]=useState(false);
 type Message={
 role:string;
 content:string;
}


const [messages,setMessages]=useState<Message[]>([]);
const [copiedMessageIndex,setCopiedMessageIndex]=useState<number | null>(null);

const chatBoxRef = useRef<HTMLDivElement>(null);
const abortControllerRef = useRef<AbortController | null>(null);

useEffect(() => {
  const chatBox = chatBoxRef.current;

  if (!chatBox) {
    return;
  }

  chatBox.scrollTo({
    top: chatBox.scrollHeight,
    behavior: "smooth"
  });
}, [messages]);

  async function sendQuestion(){

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || loading) {
      return;
    }

    const controller = new AbortController();
    abortControllerRef.current = controller;

    setLoading(true);
    const userMessage = {
  role: "user",
  content: trimmedQuestion
};

const nextMessages = [...messages, userMessage];
const placeholderIndex = nextMessages.length;

setMessages([
  ...nextMessages,
  {
    role: "ai",
    content: ""
  }
]);

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/api/chat",
        {
          method: "POST",

          headers: {
            "Content-Type": "application/json"
          },

         body: JSON.stringify({
  messages: nextMessages
}),
          signal: controller.signal
        }
      );

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const reader = response.body?.getReader();

      if (!reader) {
        throw new Error("Response body is not readable");
      }

      const decoder = new TextDecoder();
      let buffer = "";

      const handleEvent = (event: string) => {
        const dataLine = event
          .split("\n")
          .find(line => line.startsWith("data:"));

        if (!dataLine) {
          return;
        }

        const payload = dataLine.slice(5).trimStart();

        if (payload === "[DONE]") {
          return;
        }

        const data = JSON.parse(payload) as {
          content?: string;
          error?: string;
        };

        if (data.error) {
          throw new Error(data.error);
        }

        if (typeof data.content !== "string") {
          return;
        }

        if (abortControllerRef.current !== controller) {
          return;
        }

        setMessages(prev =>
          prev.map((message, index) =>
            index === placeholderIndex
              ? { ...message, content: message.content + data.content }
              : message
          )
        );
      };

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        events.forEach(handleEvent);
      }

      buffer += decoder.decode();

      if (buffer.trim()) {
        handleEvent(buffer);
      }

      setQuestion("");
    } catch (error) {
      if (
        controller.signal.aborted ||
        (error instanceof Error && error.name === "AbortError")
      ) {
        return;
      }

      setMessages(prev => [
        ...prev.map((message, index) =>
          index === placeholderIndex
            ? {
                ...message,
                content: message.content
                  ? `${message.content}\n\n请求失败，请检查网络连接或稍后重试。`
                  : "请求失败，请检查网络连接或稍后重试。"
              }
            : message
        )
      ]);
    } finally {
      if (abortControllerRef.current === controller) {
        setLoading(false);
        abortControllerRef.current = null;
      }
    }
}

function stopGeneration() {
  abortControllerRef.current?.abort();
}

function resetConversation() {
  abortControllerRef.current?.abort();
  setMessages([]);
  setQuestion("");
  setLoading(false);
  setCopiedMessageIndex(null);
  abortControllerRef.current = null;
}

async function copyAiMessage(index: number, content: string) {
  try {
    await navigator.clipboard.writeText(content);
    setCopiedMessageIndex(index);

    window.setTimeout(() => {
      setCopiedMessageIndex(current =>
        current === index ? null : current
      );
    }, 1500);
  } catch (error) {
    console.error("复制失败", error);
  }
}

  return (
  <div className="app">

    <aside className="sidebar">
      <button
        className="new-chat-button"
        onClick={resetConversation}
      >
        新建对话
      </button>

      <button
        className="clear-chat-button"
        onClick={resetConversation}
      >
        清空对话
      </button>
    </aside>

    <main className="chat-area">
      <h1>
        DMU AI学习助手
      </h1>

      <div className="chat-box" ref={chatBoxRef}>

        {
          messages.map((message,index)=>(
            message.role === "ai" && message.content === ""
              ? null
              :
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

              {
                message.role === "user"
                  ? message.content
                  : <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
              }

              {
                message.role === "ai" &&
                message.content !== "" &&
                !(loading && index === messages.length - 1) && (
                  <button
                    type="button"
                    className="copy-button"
                    onClick={() => copyAiMessage(index, message.content)}
                  >
                    {copiedMessageIndex === index ? "已复制" : "复制"}
                  </button>
                )
              }

            </div>

          ))
        }
        {
 loading && messages[messages.length - 1]?.content === "" && (
   <div className="message ai">
      AI正在思考...
   </div>
 )
}
      


      </div>


      <div className="input-area">

       <textarea
  value={question}
  onChange={(event)=>setQuestion(event.target.value)}
  placeholder="请输入你的问题"
  rows={3}

  onKeyDown={(event)=>{

    if(
      event.key==="Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ){

      event.preventDefault();
      sendQuestion();

    }

  }}
/>

        <button
      onClick={loading ? stopGeneration : sendQuestion}
      >
      {loading ? "停止生成" : "发送"}
      </button>


      </div>
    </main>


  </div>
);
}

export default App;
