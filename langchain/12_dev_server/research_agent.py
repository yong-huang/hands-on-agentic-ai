"""
12 · 本地服务化总装：迷你研究助手（langgraph dev 的图入口）

三个能力装进一张图：
  - 检索工具 search_repo_docs：懒加载仓库 docs/ 的 Chroma 索引，回答标注来源
  - 危险工具 delete_note：删除笔记前经 HumanInTheLoopMiddleware 审批
  - 追踪回调 ServerTracer：llm / 工具事件写 JSONL（图级 with_config 挂载）

由 langgraph.json 以 "research_agent": "./research_agent.py:graph" 暴露给
langgraph dev 服务；客户端脚本 dev_server.py 通过 SDK 调用。
"""

import json
import time
from pathlib import Path
from typing import Annotated

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tools import tool

HERE = Path(__file__).resolve().parent
DOCS_DIR = HERE.parents[1] / "docs"
TRACE_PATH = HERE / "trace_server.jsonl"
DELETED_LOG = HERE / "deleted_notes.txt"

_STORE = None


def _get_store():
    """懒加载向量索引：首次检索时构建，避免服务启动就依赖嵌入模型。"""
    global _STORE
    if _STORE is None:
        from langchain_chroma import Chroma
        from langchain_core.documents import Document
        from langchain_ollama import OllamaEmbeddings
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(chunk_size=400, chunk_overlap=60)
        chunks = []
        for f in sorted(DOCS_DIR.glob("*.md")):
            for c in splitter.split_text(f.read_text(encoding="utf-8")):
                chunks.append(Document(page_content=c, metadata={"source": f.name}))
        import tempfile
        _STORE = Chroma(collection_name="server_docs",
                        embedding_function=OllamaEmbeddings(model="nomic-embed-text"),
                        persist_directory=tempfile.mkdtemp(prefix="srv_index_"))
        _STORE.add_documents(chunks)
    return _STORE


@tool
def search_repo_docs(query: Annotated[str, "检索关键词或问题"]):
    """检索本仓库 docs/ 文档库，返回最相关的片段与来源文件名。"""
    hits = _get_store().similarity_search(query, k=3)
    return "\n\n".join(f"[{h.metadata['source']}] {h.page_content[:300]}" for h in hits)


@tool
def delete_note(name: Annotated[str, "要删除的笔记文件名"]):
    """删除一条笔记（危险操作，执行前需要人工审批）。"""
    with open(DELETED_LOG, "a", encoding="utf-8") as f:
        f.write(name + "\n")
    return f"已删除笔记 {name}"


class ServerTracer(BaseCallbackHandler):
    """服务端追踪：把模型与工具事件追加写入 JSONL。"""

    def __init__(self, path: Path):
        super().__init__()
        self.path = path

    def _write(self, **payload):
        payload["ts"] = round(time.time(), 3)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def on_llm_start(self, serialized, prompts, *, run_id, **kw):
        self._write(event="llm_start", name=(serialized or {}).get("name") or "llm")

    def on_llm_end(self, response, *, run_id, **kw):
        usage = {}
        try:
            usage = response.generations[0][0].message.usage_metadata or {}
        except Exception:
            pass
        self._write(event="llm_end", input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"))

    def on_tool_start(self, serialized, input_str, *, run_id, **kw):
        self._write(event="tool_start", name=(serialized or {}).get("name") or "tool")

    def on_tool_end(self, output, *, run_id, **kw):
        self._write(event="tool_end")


from langchain_ollama import ChatOllama

_model = ChatOllama(model="qwen3.8:latest", reasoning=False,
                    temperature=0, num_predict=512)

# 注意：这里不挂 checkpointer——langgraph dev 由平台注入持久化
# （自备 checkpointer 会在服务加载时被拒绝："persistence is handled
# automatically by the platform"），HumanInTheLoop 的中断/恢复由平台接管。
_agent = create_agent(
    model=_model,
    tools=[search_repo_docs, delete_note],
    middleware=[HumanInTheLoopMiddleware(
        interrupt_on={"delete_note": {
            "allowed_decisions": ["approve", "edit", "reject"],
        }},
    )],
    system_prompt=(
        "你是研究助手。回答仓库相关问题时必须先调用 search_repo_docs 检索，"
        "答案末尾标注 [来源: 文件名]；被要求删除笔记时调用 delete_note。"
    ),
)

# 图级挂载追踪回调（with_config 返回的仍是 CompiledStateGraph，可直接被服务加载）
graph = _agent.with_config({"callbacks": [ServerTracer(TRACE_PATH)]})
