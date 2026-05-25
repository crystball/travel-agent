# Travel Agent 旅游规划助手

这是一个基于 **LangGraph** 的旅游规划 Agent 项目。用户输入一段自然语言旅行需求后，系统会调用景点、交通、酒店、天气、预算和行程规划模块，最终生成命令行摘要和一份本地 HTML 旅游指南页面。

示例输入：

```text
2人从上海出发，2026-06-01到2026-06-03去杭州，预算3000，喜欢西湖、美食
```

系统会输出：

- 需求解析
- 景点推荐
- 交通方案
- 酒店推荐
- 预算分析
- 最终行程
- HTML 网页版旅游指南

---

## 项目组成

```text
travel-agent/
├─ main.py                  # 命令行入口，运行 workflow 并输出结果/HTML
├─ workflow.py              # LangGraph 工作流编排
├─ state.py                 # 全局状态与数据模型
├─ html_renderer.py         # HTML 旅游指南渲染器
├─ date_utils.py            # 日期解析、查询窗口判断
├─ geo_utils.py             # 经纬度距离计算
├─ timing_utils.py          # 节点耗时统计与部分 LLM 开关
├─ flyai_client.py          # FlyAI CLI 调用封装：景点、酒店、机票
├─ mcp_12306_client.py      # 12306 MCP 调用封装：高铁/动车
├─ transport_clients.py     # 交通/酒店外部服务聚合入口
├─ weather_client.py        # 心知天气 API 客户端
├─ llm_client.py            # DeepSeek/OpenAI-compatible LLM 客户端
├─ agents/
│  ├─ needs_analysis.py     # 需求解析 Agent
│  ├─ attraction.py         # 景点推荐 Agent
│  ├─ transportation.py     # 交通规划 Agent
│  ├─ booking.py            # 酒店推荐 Agent
│  ├─ budget.py             # 预算分析 Agent
│  └─ itinerary.py          # 行程生成 Agent
├─ requirements.txt         # Python 依赖
├─ .env.example             # 环境变量示例
└─ design.md                # 项目设计说明
```

---

## 工作流概览

项目使用 LangGraph 编排核心流程：

```text
用户自然语言输入
  ↓
需求解析 needs_analysis
  ↓
构建路由信息 build_routing_info
  ↓
景点推荐 attraction ──→ 酒店推荐 booking
  ↓                       ↓
交通规划 transportation ─┘
  ↓
汇总 join_results
  ↓
预算分析 budget
  ↓
行程生成 itinerary
  ↓
命令行输出 / HTML 指南
```

其中：

- 景点和酒店会尽量结合用户偏好与经纬度；
- 酒店推荐优先考虑靠近首日景点，并尽量提供不同价位；
- 交通会同时保留高铁/动车和飞机方案，供用户自行选择；
- 预算分析仅计入核心费用：交通、酒店、已知景点门票；
- 天气仅在 API 能覆盖完整行程日期时展示，否则提示超出查询范围；
- HTML 页面用于最终面向用户展示。

---

## 外部服务依赖

项目当前使用这些外部服务：

### 1. DeepSeek / OpenAI-compatible LLM

用于：

- 需求解析；
- 可选的景点推荐增强；
- 可选的行程生成。

默认模型配置来自：

```env
LLM_BASE_URL="https://api.deepseek.com"
LLM_API_KEY="sk-your-deepseek-key"
LLM_MODEL="deepseek-v4-pro"
```

### 2. FlyAI / 飞猪 AI

用于：

- 景点搜索；
- 酒店搜索；
- 机票搜索。

配置：

```env
FLYAI_API_KEY="your-flyai-api-key"
FLYAI_COMMAND="flyai"
```

需要本机能运行：

```powershell
flyai --help
```

### 3. 12306 MCP

用于：

- 高铁/动车票查询。

配置：

```env
MCP_12306_COMMAND="npx"
MCP_12306_ARGS="-y 12306-mcp"
```

### 4. 心知天气 Seniverse

用于：

- 行程天气预报。

配置：

```env
SENIVERSE_API_KEY="your-seniverse-api-key"
SENIVERSE_LANGUAGE="zh-Hans"
SENIVERSE_UNIT="c"
SENIVERSE_MAX_FORECAST_DAYS="14"
```

天气逻辑：

- 如果天气 API 能覆盖完整行程日期，则展示每天的天气和温度；
- 如果有任意一天超出查询范围，则不展示每日天气，并提示超出天气查询范围。

---

## 环境准备

建议使用 Python 3.11。

### 1. 创建并进入环境

如果你使用 conda：

```powershell
conda create -n travel python=3.11
conda activate travel
```

### 2. 安装 Python 依赖

```powershell
cd path\to\travel-agent
pip install -r requirements.txt
```

### 3. 安装/确认 Node.js 与 npm

12306 MCP 和 FlyAI CLI 依赖 Node/npm。

```powershell
node -v
npm -v
```

### 4. 配置 `.env`

复制示例文件：

```powershell
copy .env.example .env
```

然后填写真实 key。

注意：`.env` 包含密钥，不要提交到公开仓库。

---

## 运行项目

在项目目录下运行：

```powershell
cd path\to\travel-agent
```

### 只输出命令行结果

```powershell
python .\main.py -i "2人从上海出发，2026-06-01到2026-06-03去杭州，预算3000，喜欢西湖、美食"
```

### 同时生成 HTML 指南

```powershell
python .\main.py -i "2人从上海出发，2026-06-01到2026-06-03去杭州，预算3000，喜欢西湖、美食" --html travel_guide.html
```

打开生成的网页：

```powershell
start .\travel_guide.html
```

### 输出完整 JSON 状态

```powershell
python .\main.py -i "2人从上海出发，2026-06-01到2026-06-03去杭州，预算3000，喜欢西湖、美食" --json
```

---

## 测试外部服务

### FlyAI 景点搜索

```powershell
flyai search-poi --city-name "杭州" --keyword "西湖"
```

### FlyAI 酒店搜索

```powershell
flyai search-hotel --dest-name "杭州" --poi-name "西湖" --check-in-date "2026-06-01" --check-out-date "2026-06-03" --sort rate_desc
```

### FlyAI 机票搜索

示例命令可根据 FlyAI CLI 文档调整：

```powershell
flyai search-flight --dep-city-name "上海" --arr-city-name "杭州" --dep-date "2026-06-01"
```

### 心知天气

从今天开始查 3 天：

```powershell
$key = ((Get-Content .env | Where-Object { $_ -match '^SENIVERSE_API_KEY=' }) -replace '^SENIVERSE_API_KEY=', '').Trim().Trim('"').Trim("'")
curl "https://api.seniverse.com/v3/weather/daily.json?key=$key&location=hangzhou&language=zh-Hans&unit=c&start=0&days=3"
```

如果查未来第 7 天开始的 3 天：

```powershell
$key = ((Get-Content .env | Where-Object { $_ -match '^SENIVERSE_API_KEY=' }) -replace '^SENIVERSE_API_KEY=', '').Trim().Trim('"').Trim("'")
curl "https://api.seniverse.com/v3/weather/daily.json?key=$key&location=hangzhou&language=zh-Hans&unit=c&start=7&days=3"
```

---

## 调试与开关

### 节点耗时统计

默认开启，会输出：

```text
[timing] needs_analysis: 6.71s
[timing] attraction: 3.20s
[timing] transportation: 1.90s
```

关闭：

```powershell
$env:TRAVEL_AGENT_TIMING="0"
```

开启：

```powershell
$env:TRAVEL_AGENT_TIMING="1"
```

### 景点推荐 LLM

默认关闭，使用规则推荐。

开启：

```powershell
$env:TRAVEL_AGENT_ATTRACTION_LLM="1"
```

关闭：

```powershell
$env:TRAVEL_AGENT_ATTRACTION_LLM="0"
```

### 行程生成 LLM

默认关闭，使用规则行程。

开启：

```powershell
$env:TRAVEL_AGENT_ITINERARY_LLM="1"
```

关闭：

```powershell
$env:TRAVEL_AGENT_ITINERARY_LLM="0"
```

---

## 当前输出说明

### 景点推荐

会展示：

- 景点名称；
- 图片；
- 推荐理由；
- 简介；
- 地址；
- 门票状态。

门票分为：

```text
免费
已知收费
收费但价格未知
待确认
```

### 交通规划

会展示多个推荐交通方案，例如：

```text
飞机
高铁/动车
```

并包含：

- 出发/到达城市或机场；
- 班次；
- 出发/到达时间；
- 价格；
- 订票链接；
- 换乘提醒。

### 酒店推荐

会最多推荐 3 个酒店，优先：

```text
靠近首日景点
覆盖不同价格档位
```

酒店价格中：

```text
¥1xx -> 展示 100 元起/晚，预算按中位数估算
¥2xx -> 展示 200 元起/晚，预算按中位数估算
```

### 预算分析

预算只计入：

```text
交通
酒店
已知景点门票
```

不计入：

```text
餐饮
市内交通
购物
临时消费
```

并默认为用户预留一部分预算空间。

### 最终行程

行程目前展示：

- 每天上午景点；
- 每天下午景点；
- 酒店到景点、景点到景点的交通参考；
- 如果天气完整可查，展示每天的天气和温度。

不会生成不可靠的餐饮和晚间安排。

---

## 常见问题

### 1. 为什么天气没有展示？

如果行程中任意一天超出心知天气 API 的可查询范围，系统不会展示半截天气，而是提示超出查询范围。

可通过：

```env
SENIVERSE_MAX_FORECAST_DAYS=14
```

控制当前账号支持的最大天气查询窗口。

### 2. 为什么酒店价格是“元起”？

FlyAI 在部分情况下返回的是模糊价格：

```text
¥1xx
¥2xx
¥5xx
```

因此展示为“起价”，预算中按中位数估算。

### 3. 为什么有些景点门票未计入预算？

如果 API 标记景点收费，但没有返回具体票价，系统会将其列出提醒，但不会强行编造价格。

### 4. 为什么运行时间有时较长？

主要耗时来自：

- 外部 API；
- FlyAI CLI；
- 12306 MCP；
- LLM 调用。

可以通过 timing 输出定位耗时节点。

---

## 后续可改进方向

- 本地 Web 表单输入旅行需求；
- 任务进度条；
- 查询缓存；
- 更精确的地图路线时间；
- PDF 导出；
- 更丰富的酒店筛选；
- 更稳定的餐厅数据源。
