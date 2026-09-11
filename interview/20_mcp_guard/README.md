# 20 · MCP Server 安全加固

> 覆盖面试题：MCP Server 的安全考量有哪些？
> 给项目 19 的书店 Server 包一层服务端安全网关：①参数白名单（字段/
> 类型/范围）②只读/读写权限分离 ③调用审计 JSONL ④每 client 限速
> ⑤参数注入特征扫描（提示词/SQL）。5 条恶意调用 + 3 条正常回归验证。

## 1. 运行与实测

```bash
MOCK=1 python mcp_guard.py    # 打安全网关 (拦截矩阵)
python mcp_guard.py serve     # 亦可作为加固版 MCP Server 被 stdio 拉起
```

实测（2026-09-09）：

| 攻击 | 拦截层 | 结果 |
|:--|:--|:--|
| 白名单外字段 admin=true | whitelist | ✓ 拒绝 |
| qty=1000000 超范围 | whitelist | ✓ 拒绝 |
| sku 藏 `drop table users;--` | injection | ✓ 拦截 |
| sku 藏"忽略之前所有指令…" | injection | ✓ 拦截 |
| 只读会话调 place_order | permission | ✓ 拒绝 |

**拦截 5/5，正常调用 3/3 不受影响，审计日志 8 条**（每条含
client/tool/verdict/layer/args）。

## 2. 深入要点

- 服务端是唯一可信边界：客户端/模型侧的约束都能被注入绕过；白名单、
  权限、限速必须在 server 侧强制执行。
- 读写分离 + 白名单外字段直接拒：最小权限不是口号，是 schema。
- 注入检测盯参数：工具参数是模型可控输入，藏在里面的指令与网页注入
  同源同罪；每条拦截都要留审计（谁/何时/哪层/为什么）。
- 分层纵深：限速挡滥用 → 权限挡越权 → 白名单挡畸形 → 注入扫描挡劫持
  → 才轮到业务逻辑。

## 3. 文件结构

```
interview/20_mcp_guard/
├── README.md            # 本篇
└── mcp_guard.py         # 业务 Server + 五层网关 + 攻击矩阵（约 200 行）
```
