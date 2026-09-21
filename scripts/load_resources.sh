#!/usr/bin/env bash
# =============================================================================
# 公共资源预载 — 解决本系列最普遍的环境阻塞: 本地模型缺失 / Ollama 未启动
#
# 本系列全部实验依赖两个本地模型 (无需任何 API Key):
#   qwen3.8:latest         对话/推理 (所有实验)
#   nomic-embed-text:latest 向量嵌入 (17/18/19 的记忆与检索)
#
# 同时幂等安装 requirements.txt 中的 Python 依赖 (装入当前 Python 环境,
# 建议先激活虚拟环境/conda 环境再运行本脚本)。
#
# 幂等: 已装好的依赖不重复下载, 已运行的服务不重复启动, 已拉取的模型不重复下载。
# 被各实验 README 的"环境要求"引用; clone 后先跑一遍本脚本即可开始学习。
# =============================================================================
set -euo pipefail

MODELS=("qwen3.8:latest" "nomic-embed-text:latest")
API="http://localhost:11434"

wait_api() {
    local i
    for i in $(seq 1 30); do
        if curl -s --max-time 2 "$API/api/tags" > /dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    echo "错误: Ollama 服务在 30 秒内未就绪，请手动启动后重试。" >&2
    return 1
}

# ---------- 1) 确保实验所需的 Python 依赖已安装 ----------
echo "=====> [python] 检查 Python 依赖"
PY="${PYTHON:-python3}"
if ! command -v "$PY" > /dev/null 2>&1; then
    echo "错误: 未找到 python3, 请先安装 Python 3.11+。" >&2
    exit 1
fi
echo "  安装目标环境: $("$PY" -c 'import sys; print(sys.executable)')"
REQ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/requirements.txt"
if "$PY" -m pip install -q -r "$REQ"; then
    echo "  依赖已就绪 (缺失的已自动安装)"
else
    echo "错误: pip 安装失败 (详见上方 pip 输出)。" >&2
    echo "  若提示 externally-managed-environment, 请先激活虚拟环境后重试," >&2
    echo "  或手动执行: $PY -m pip install -r $REQ" >&2
    exit 1
fi

# ---------- 2) 确保 Ollama 服务在运行 ----------
echo "=====> [service] 检查 Ollama 服务"
if curl -s --max-time 2 "$API/api/tags" > /dev/null 2>&1; then
    echo "  已在运行: $API"
else
    echo "  未运行, 尝试启动 ollama serve (后台)..."
    if command -v ollama > /dev/null 2>&1; then
        nohup ollama serve > /tmp/ollama_serve.log 2>&1 &
    elif [ "$(uname)" = "Darwin" ] && [ -d "/Applications/Ollama.app" ]; then
        open -a Ollama
    else
        echo "错误: 未找到 ollama，请先安装: https://ollama.com/download" >&2
        exit 1
    fi
    wait_api
    echo "  服务已就绪"
fi

# ---------- 3) 确保所需模型已拉取 ----------
echo "=====> [models] 检查并预拉模型"
existing="$(ollama list 2>/dev/null | awk '{print $1}')"
for model in "${MODELS[@]}"; do
    if echo "$existing" | grep -qx "$model"; then
        echo "  已存在: $model"
    else
        echo "  拉取: $model (首次下载较大, 请耐心等待)..."
        ollama pull "$model"
    fi
done

# ---------- 4) 验证 ----------
echo "=====> [verify] 冒烟验证"
qwen_ok="$(curl -s --max-time 120 "$API/api/chat" -d \
    '{"model":"qwen3.8:latest","messages":[{"role":"user","content":"回复 OK"}],"stream":false,"think":false,"options":{"num_predict":5}}' \
    | grep -c '"content"' || true)"
embed_ok="$(curl -s --max-time 60 "$API/api/embeddings" -d \
    '{"model":"nomic-embed-text","prompt":"test"}' \
    | grep -c '"embedding"' || true)"
echo "  chat 接口: $([ "$qwen_ok" -ge 1 ] && echo 可用 || echo 异常)"
echo "  embeddings 接口: $([ "$embed_ok" -ge 1 ] && echo 可用 || echo 异常)"
echo "=====> 完成。可以开始学习: 从 agents/01_call_llm/ 开始。"
