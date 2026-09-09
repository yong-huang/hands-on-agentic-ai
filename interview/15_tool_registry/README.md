# 15 · 工具注册表与 Schema 设计

> 覆盖面试题：Function Calling 的 JSON Schema 怎么设计？嵌套参数怎么处理？
> 装饰器式工具注册表：从函数签名 + docstring 自动生成 JSON Schema（描述
> 自动进字段）；嵌套参数（数组内对象/对象内对象）显式声明，jsonschema
> 校验；错误友好化 = 路径 + 期望 vs 实际 + 修正提示，结构化喂回模型。

## 1. 运行与实测

```bash
MOCK=1 python tool_registry.py    # 离线: 预置模型纠错
python tool_registry.py           # 真实: qwen3.8 读错误后自行纠正
```

实测（2026-09-09，qwen3.8）：5 个含嵌套参数的工具合法调用全通；
3 条故意错参（qty 违反 minimum / 缺 to_city / op 不在枚举）均收到带
路径的结构化错误，模型读错误后自行纠正 3/3 ✓：

```
create_order:  参数 items.0.qty 校验失败: 0 is less than the minimum of 1
query_flights: 参数 route 校验失败: 'to_city' is a required property
configure_alert: 参数 rules.0.op 校验失败: '≈' is not one of ['>', '<']
→ 模型修正后 3/3 通过
```

## 2. 设计要点

- Schema 是给模型看的 API 文档：类型 + 枚举 + 描述缺一不可；docstring
  的 `参数名: 说明` 行自动变成字段 description（单一事实源）。
- 嵌套参数用 items.properties 显式声明；校验错误必须带路径
  （items[0].qty）——没有路径的报错模型修不了。
- 错误友好化 = 结构化（code/message/hint），不是堆栈字符串；模型读得懂
  错误才能自行纠正，这是 Agent 稳定性的隐藏关键。
- 基本类型从签名注解推导（未注解默认 string——实测踩坑：amount 不加
  `int` 注解导致 500 被判类型错误）。

## 3. 文件结构

```
interview/15_tool_registry/
├── README.md            # 本篇
└── tool_registry.py     # @tool 注册表 + jsonschema 校验 + 纠错实验（约 240 行）
```
