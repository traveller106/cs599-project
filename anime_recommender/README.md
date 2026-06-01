# 基于 LangGraph 的多智能体动漫推荐系统

一个使用 LangGraph 编排的多智能体动漫推荐系统，结合 DeepSeek Chat API、Bangumi 动漫数据库和 Tavily 网络搜索，通过 Streamlit 提供直观的聊天界面。

## 功能特性

- 💬 自然语言交互：用中文描述你想看的动漫类型
- 🤖 多智能体协作：意图理解 → 搜索 → 推荐生成 → 评估反思
- 🔄 反思循环：AI 批评家自动评估推荐质量，不通过则修正重试
- ⚡ 并行搜索：同时从 Bangumi 数据库和网络获取信息
- 🎛️ 硬性过滤器：类型、年代、评分、标签多维度筛选
- 📊 状态可视化：Tavily 搜索用量、执行路径一目了然

## 安装

```bash
# 克隆项目后进入目录
cd anime_recommender

# 安装依赖
pip install -r requirements.txt
```

## 配置

1. 复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，填入你的 API 密钥：

```
DEEPSEEK_API_KEY=你的DeepSeek_API密钥
TAVILY_API_KEY=你的Tavily_API密钥
```

- DeepSeek API 密钥获取：https://platform.deepseek.com/api_keys
- Tavily API 密钥获取：https://app.tavily.com/

## 运行

```bash
streamlit run app.py
```

然后在浏览器中打开 http://localhost:8501 即可使用。

## 项目结构

```
anime_recommender/
├── app.py              # Streamlit 入口，管理会话与界面
├── graph.py            # LangGraph 图定义与编译
├── agents.py           # 每个节点的具体实现逻辑
├── tools.py            # Bangumi / Tavily API 工具
├── state.py            # AgentState 定义
├── ui_components.py    # Streamlit 小组件（卡片、过滤器等）
├── .env.example        # API 密钥模板
├── requirements.txt    # 依赖列表
└── README.md           # 项目说明
```

## 技术栈

- **编排框架**: LangGraph
- **大模型**: DeepSeek Chat API
- **搜索工具**: Tavily Search API
- **动漫数据库**: Bangumi API
- **前端界面**: Streamlit