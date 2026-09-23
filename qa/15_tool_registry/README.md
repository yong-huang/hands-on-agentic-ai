# 15 · 工具注册表与 Schema 设计

> 装饰器式工具注册表：从函数签名 + docstring 自动生成 JSON Schema
> （描述自动进字段）；嵌套参数（数组内对象/对象内对象）显式声明，
> jsonschema 校验；错误友好化 = 路径 + 期望 vs 实际 + 修正提示，结构化
> 喂回模型。

## What

工具注册表把"函数"变成"模型可调用的工具"，三件事决定调用质量：

- **Schema 自动生成**：类型 + 枚举 + 描述缺一不可；docstring 的
  `参数名: 说明` 行自动变成字段 description（单一事实源）；
- **嵌套参数**用 `items.properties` 显式声明，jsonschema 校验；
- **错误友好化**：结构化（code/message/hint），不是堆栈字符串。

心智模型一句话：**Schema 是给模型看的 API 文档——模型读得懂错误才能
自行纠正，这是 Agent 稳定性的隐藏关键。**

## Why

Function Calling 的稳定性一半取决于 schema 质量、一半取决于出错后模型
能不能被错误信息拉回来。错误不带路径、不带期望值，模型就只能瞎猜重试
——schema 与错误设计要一起做实验验证。

## How

```bash
cd qa/15_tool_registry
MOCK=1 python3 tool_registry.py    # 离线: 预置模型纠错
python3 tool_registry.py           # 真实: qwen3.8 读错误后自行纠正
```

实测：5 个含嵌套参数的工具合法调用全通；3 条故意错参（qty 违反 minimum /
缺 to_city / op 不在枚举）均收到带路径的结构化错误，模型读错误后自行
纠正 3/3 ✓：

```
create_order:  参数 items.0.qty 校验失败: 0 is less than the minimum of 1
query_flights: 参数 route 校验失败: 'to_city' is a required property
configure_alert: 参数 rules.0.op 校验失败: '≈' is not one of ['>', '<']
→ 模型修正后 3/3 通过
```

## Deep Dive

**校验错误必须带路径**（`items[0].qty`）——没有路径的报错模型修不了：
它不知道错误发生在数组第几个元素、哪个字段。路径 + 期望 vs 实际 + 修正
提示三件齐了，"错误回传 → 自纠"闭环才成立。

踩坑清单：

- **未注解参数默认 string**：`amount` 不加 `int` 注解，500 被判类型
  错误——签名注解是 schema 的源头，源头错全链错。

## Q&A

**Q1: 嵌套参数怎么声明？**

用 `items.properties` 显式声明数组内对象/对象内对象的结构，交给
jsonschema 校验——嵌套结构的错误尤其依赖路径信息（`items.0.qty`），
这也是嵌套参数必须走显式 schema 而不是自由 JSON 的原因。
