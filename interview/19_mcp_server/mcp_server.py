"""
面试项目 19 — MCP Server 实战

覆盖面试题: MCP 解决了什么问题？三种原语 (Resources/Tools/Prompts)？
如何设计一个 MCP Server？

核心: 用官方 Python SDK (FastMCP) 写一个书店库存 MCP Server:
  Tools     query_stock / place_order / sales_stats   (模型可调用的动作)
  Resource  inventory://view                          (只读数据视图, 应用拉取)
  Prompt    order_help                                (可复用的话术模板)
stdio 传输; test 子命令起子进程服务器, 用 ClientSession 做连通测试:
list 全部能力 → 逐个调用 → 打印结果。协议测试不依赖 LLM。

运行:
  python mcp_server.py serve    # 起服务器 (stdio, 一般由客户端拉起)
  python mcp_server.py test     # 连通测试: list + call 全部能力
"""

import asyncio, json, os, sys
from datetime import datetime

from mcp.server.mcpserver import MCPServer   # mcp 2.x (FastMCP 已改名)

mcp = MCPServer("bookstore")

DB = {                                   # 内存库存
    'A1': {'name': '深入理解TCP/IP', 'stock': 12, 'price': 89.0},
    'A2': {'name': '设计数据密集型应用', 'stock': 3, 'price': 128.0},
    'A3': {'name': '流畅的Python', 'stock': 0, 'price': 139.0},
}
ORDERS = []


@mcp.tool()
def query_stock(sku: str) -> str:
    """查询图书库存与价格"""
    b = DB.get(sku)
    if not b:
        return json.dumps({'ok': False, 'error': f'未知 sku: {sku}'},
                          ensure_ascii=False)
    return json.dumps({'ok': True, 'sku': sku, 'name': b['name'],
                       'stock': b['stock'], 'price': b['price']},
                      ensure_ascii=False)


@mcp.tool()
def place_order(sku: str, qty: int) -> str:
    """下单购买图书 (扣减库存)"""
    b = DB.get(sku)
    have = b['stock'] if b else 0
    if not b or b['stock'] < qty:
        return json.dumps({'ok': False,
                           'error': f'库存不足: 需要 {qty}, 现有 {have}'},
                          ensure_ascii=False)
    b['stock'] -= qty
    order = {'order_id': f'O{len(ORDERS) + 1:03d}', 'sku': sku, 'qty': qty,
             'amount': round(b['price'] * qty, 2),
             'ts': datetime.now().isoformat(timespec='seconds')}
    ORDERS.append(order)
    return json.dumps({'ok': True, **order}, ensure_ascii=False)


@mcp.tool()
def sales_stats(days: int = 7) -> str:
    """统计最近 N 天的订单数与销售额"""
    recent = ORDERS[-days:] if days else ORDERS
    total = round(sum(o['amount'] for o in recent), 2)
    return json.dumps({'orders': len(recent), 'amount': total},
                      ensure_ascii=False)


@mcp.resource('inventory://view')
def inventory_view() -> str:
    """库存只读视图 (给应用/人看, 不占用模型工具调用)"""
    lines = [f"{sku}\t{b['name']}\tstock={b['stock']}\t¥{b['price']}"
             for sku, b in sorted(DB.items())]
    return 'sku\t书名\t库存\t单价\n' + '\n'.join(lines)


@mcp.prompt()
def order_help(sku: str) -> str:
    """生成订单处理话术模板"""
    b = DB.get(sku, {'name': sku, 'stock': 0})
    return (f"顾客想购买《{b['name']}》(当前库存 {b['stock']})。"
            '请: 1) 确认库存 2) 给出下单建议 3) 提醒支付方式。')


# ============================================================
# 连通测试 (MCP 客户端, 子进程拉起 stdio 服务器)
# ============================================================

async def run_test():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=sys.executable,
                                   args=[os.path.abspath(__file__), 'serve'])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print('==> 会话初始化成功 (协议握手)')

            tools = await session.list_tools()
            print(f"==> Tools ({len(tools.tools)}): "
                  f"{[t.name for t in tools.tools]}")
            resources = await session.list_resources()
            print(f"==> Resources ({len(resources.resources)}): "
                  f"{[str(r.uri) for r in resources.resources]}")
            prompts = await session.list_prompts()
            print(f"==> Prompts ({len(prompts.prompts)}): "
                  f"{[p.name for p in prompts.prompts]}")

            print('\n==> 调用 tool: query_stock(A1)')
            r = await session.call_tool('query_stock', {'sku': 'A1'})
            print('   ', r.content[0].text)

            print('==> 调用 tool: place_order(A1, qty=2)')
            r = await session.call_tool('place_order', {'sku': 'A1', 'qty': 2})
            print('   ', r.content[0].text)

            print('==> 调用 tool: place_order(A3, qty=1)  (零库存, 期待失败)')
            r = await session.call_tool('place_order', {'sku': 'A3', 'qty': 1})
            print('   ', r.content[0].text)

            print('==> 调用 tool: sales_stats(days=7)')
            r = await session.call_tool('sales_stats', {'days': 7})
            print('   ', r.content[0].text)

            print('==> 读取 resource: inventory://view')
            r = await session.read_resource('inventory://view')
            print('   ' + r.contents[0].text.replace(chr(10), chr(10) + '   '))

            print('==> 获取 prompt: order_help(sku=A2)')
            r = await session.get_prompt('order_help', {'sku': 'A2'})
            print('   ', r.messages[0].content.text[:64], '...')


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ('serve', 'test'):
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == 'serve':
        mcp.run()                    # stdio 传输 (默认)
    else:
        asyncio.run(run_test())


if __name__ == "__main__":
    main()
