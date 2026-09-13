# 智能电商采购 Agent

个人定制购物助手：通过对话理解用户需求（预算、平台偏好、学生身份、性价比/品质取向），聚合淘宝 / 京东 / 拼多多三平台价格与优惠，输出比价、领券口令与购买建议。

## 项目结构

```
├── frontend-web/          # 网页版（Vue 3 + Vite，GitHub Pages 部署）
├── frontend/              # 移动版（Vant 版，Vue 3）
└── 智能电商采购Agent-设计方案.md   # 设计方案文档
```

## 在线访问

网页版部署于 GitHub Pages：https://szy0607.github.io/price-agent-web/

## 本地开发（网页版）

```bash
cd frontend-web
npm install
npm run dev      # 开发服务器 http://localhost:5174
npm run build    # 构建产物 dist/
```

## 部署

推送到 `main` 分支后，GitHub Actions（`.github/workflows/deploy.yml`）自动构建 `frontend-web` 并部署到 GitHub Pages。
