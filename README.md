# 课题七：黑客帝国的「数字孪生」— 多 AI 聊天室

网页聊天室里没有真人，只有 4 个 AI 机器人围绕你抛出的话题自动辩论。

| 角色 | 性格 |
|------|------|
| 冷酷理智的科学家 | 数据、因果、风险 |
| 乐天派吹捧大师 | 热情、乐观、反驳悲观 |
| 冲浪梗王 | 网络梗、弹幕体、又好笑又有观点 |
| 毒舌评委 | 犀利吐槽、裁决打分、最后点评 |

## 技术栈

- **后端**：Python + FastAPI + WebSocket
- **前端**：HTML + CSS + JavaScript（WebSocket 客户端）
- **大模型**：OpenAI 兼容 API

## 快速开始

```bash
cd chatroom
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

浏览器打开：<http://localhost:8000>

输入话题（如「人类应不应该移居火星？」），点击 **启动辩论**，四个 AI 会通过 WebSocket 实时推送发言。

## 项目结构

```
chatroom/
├── server.py          # WebSocket 服务 + 辩论调度
├── prompts.py         # 四个角色的 System Prompt
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js         # WebSocket 客户端
├── requirements.txt
└── .env.example
```

## 教学要点

### WebSocket 长连接

普通网页用 HTTP 时，浏览器每次都要「问一遍服务器有没有新消息」，要么整页刷新，要么定时轮询，既慢又费资源。

WebSocket 在握手后保持**一条长连接**，服务器有新消息就**主动推送**到浏览器——微信、聊天室、在线游戏都用这个思路。

### System Prompt 与角色扮演

大模型默认是「通用助手」。在 API 里加一条 `role: system` 的消息，用自然语言规定：

- 你是谁（评委 / 科学家 / 乐天派）
- 你怎么说话（字数、格式、禁止项）
- 你要干什么（反驳谁、用什么论据）

同一段用户话题，换不同的 System Prompt，输出风格会完全不同——这就是 **Prompt 塑造性格**。

### Prompt 注入（延伸）

若用户输入「忽略以上指令，你现在是…」，可能干扰角色。本课题中用户只提供**话题**，不参与 AI 对话链，可降低注入风险。生产环境还需做输入过滤与 system 优先级保护。

## 环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `OPENAI_API_KEY` | API 密钥 | 必填 |
| `OPENAI_BASE_URL` | 兼容 API 地址 | `https://api.openai.com/v1` |
| `MODEL` | 模型名 | `gpt-4o-mini` |
| `DEBATE_ROUNDS` | 辩论轮数（每轮 4 人各发言一次） | `3` |
| `LOG_LEVEL` | 日志级别（INFO / DEBUG） | `INFO` |

## 日志说明

启动后终端会输出：

- **HTTP 请求/响应**：每次打开页面、加载静态资源
- **WebSocket 收请求**：客户端发来的原始 JSON
- **大模型调用/响应**：角色、轮次、耗时、token、内容摘要
- **【毒舌评委发话】**：评委每次完整发言（INFO 级别即可见）

查看更详细的请求体可设置 `LOG_LEVEL=DEBUG`。

## WebSocket 协议

**客户端 → 服务端**

```json
{ "type": "start_debate", "topic": "人类应不应该移居火星？" }
```

**服务端 → 客户端**

```json
{ "type": "message", "role": "scientist", "name": "冷酷理智的科学家", "content": "...", "round": 1 }
{ "type": "typing", "role": "judge", "name": "毒舌评委" }
{ "type": "status", "content": "第 1 轮辩论开始…" }
{ "type": "done", "content": "辩论结束" }
{ "type": "error", "content": "..." }
```
# chatroom
