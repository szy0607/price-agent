# 智能导购 Agent（购物决策助手）— 前端 Demo

基于《智能电商采购Agent-设计方案.md》v0.2/v0.3 生成的移动端优先静态前端 Demo。
技术栈：Vue 3 + Vite + Vant 4 + Vue Router（Hash 模式）。

## 启动

```bash
cd frontend
npm install
npm run dev      # 开发：http://localhost:5173
npm run build    # 产物输出到 dist/，任意静态服务器可托管
npm run preview  # 本地预览构建产物
```

## 目录结构

```text
frontend/
├── index.html                 # 入口 HTML（移动端 viewport）
├── vite.config.js             # Vite 配置
├── package.json
└── src/
    ├── main.js                # 应用入口（注册 Vant / Router）
    ├── App.vue                # 布局壳 + 底部标签栏
    ├── router/index.js        # 路由（/ 、/chat、/compare、/coupon）
    ├── styles/main.css        # 全局变量与通用样式（移动优先）
    ├── mock/data.js           # Mock 数据源：商品/SKU/双价/券/平台权益矩阵
    ├── views/
    │   ├── HomeView.vue       # 首页：定位、核心原则、四步闭环、数据接口说明
    │   ├── ChatView.vue       # 对话页：文字+商品链接输入、卡片式结果
    │   ├── CompareView.vue    # 款式对比：双价矩阵 + 规格参数表 + 券明细 + 结论
    │   └── CouponGuideView.vue# 领券指引：券类型、双价口径、分平台领券步骤
    └── assets/
```

## 页面与设计稿的对应关系

| 页面 | 对应设计稿章节 |
|------|--------------|
| 首页 | §1 项目定位、§2 总体架构（统一适配层 4 接口）、§4 核心流程四步闭环 |
| 对话页 | §3.3 卡片式结果、§3.2 双价展示策略、§4 核心流程 ①-⑨ |
| 款式对比页 | §3.1 A4 款式对比 / A5 推荐引导、§3.2 联盟 API 字段 |
| 领券指引页 | §3.2 优惠类型获取策略（v0.3）、券类型、禁用评论区爬虫原则 |

## Demo 边界（与设计稿一致）

- 不代下单、不代支付，交易 100% 由用户完成
- 不提供 CPS 推广链接，只给领券路径
- 渠道专享券同时展示「能否领到」两个价格（公开价 A / 领券价 B）
- 不使用评论区数据；千人千面权益（天降红包 / 限时折扣）只做指引不做承诺
- 对话由前端 Mock 规则模拟（`mock/data.js` 的 `matchProduct`），正式版由 A1-A5 多 Agent 链路驱动

## 待接后端（下一步）

- FastAPI + LangGraph 多 Agent 编排（A1 路由 / A2 商品情报 / A3 价格情报 / A4 款式对比 / A5 推荐引导）
- 联盟查券 API 适配层：淘宝联盟 / 京东联盟 / 多多进宝 + Mock 数据源
- PostgreSQL + pgvector（RAG）与 Redis 缓存
