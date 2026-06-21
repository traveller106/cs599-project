# 基于 LangGraph 的多智能体动漫推荐系统

## 项目简介

一个使用 LangGraph 编排的多智能体动漫推荐系统，用户通过自然语言描述偏好，系统自动完成意图理解、多源搜索、推荐生成与质量评估，最终输出个性化的动漫推荐结果。

## 方向

方向一：Agentic AI 原生开发

## 技术栈

- **AI IDE**: Trae CN
- **LLM**: DeepSeek API（deepseek-chat）
- **编排框架**: LangGraph
- **前端界面**: Streamlit
- **搜索工具**: Tavily Search API
- **动漫数据库**: Bangumi API
- **容器**: Docker

## 目录结构

```
├── src/
│   ├── app.py              # Streamlit 入口，管理会话与界面交互
│   ├── graph.py            # LangGraph 图定义、节点路由与编译
│   ├── agents.py           # 各智能体节点实现（意图理解、搜索、推荐、评估）
│   ├── tools.py            # Bangumi / Tavily API 封装与数据获取
│   ├── state.py            # AgentState 类型定义
│   ├── ui_components.py    # Streamlit UI 组件（推荐卡片、过滤器等）
│   ├── .env.example        # 环境变量模板
│   └── requirements.txt    # Python 依赖
├── docs/                   # 项目文档
├── Dockerfile
├── docker-compose.yml
├── .gitignore
├── LICENSE
└── README.md
```

## 环境搭建

### 1. 环境变量配置

```bash
cd src
cp .env.example .env
```

编辑 `src/.env` 文件，填入你的 API 密钥（⚠️ 请勿将 API Key 硬编码或提交到仓库）：

```
DEEPSEEK_API_KEY=你的DeepSeek_API密钥
TAVILY_API_KEY=你的Tavily_API密钥
```

- DeepSeek API Key 获取：https://platform.deepseek.com/api_keys
- Tavily API Key 获取：https://app.tavily.com/

### 2. 启动方式

#### 方式一：Docker（推荐）

```bash
docker compose up -d
```

浏览器访问 http://localhost:8501。

#### 方式二：本地运行

```bash
cd src
pip install -r requirements.txt
streamlit run app.py
```

## 项目状态

- [x] Proposal
- [x] MVP
- [x] Final
