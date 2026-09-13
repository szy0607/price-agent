# 智能导购 Agent · 网页版前端

桌面优先的对话式购物决策助手 Demo（Vue 3 + Vite 5 + Tailwind 4 + Phosphor Icons）。

> 设计文档：`智能电商采购Agent-设计方案.md`（v0.4）｜项目进度：`.agent`

## 功能

- **智能咨询**（`/chat`）：粘贴商品链接 / 上传商品图片 / 直接提问，Mock 链路输出 情报卡 → 对比摘要 → 推荐结论 → 复制口令
- **款式对比**（`/compare`）：双价矩阵（公开价 A / 领券价 B）+ 规格表 + 券明细 + 对比结论
- **领券指引**（`/coupon`）：券类型、分平台领券步骤、权益矩阵、复制口令跳转 App

## 本地开发

```bash
npm install
npm run dev      # http://localhost:5175
npm run build    # 产物 dist/
```

## 部署

推送到 GitHub 后，仓库 Actions 自动构建并发布到 GitHub Pages（需在 Settings → Pages 选择 "GitHub Actions" 作为发布来源）。

## 合规说明

本工具仅做信息聚合与决策建议：不代下单、不代支付、不提供 CPS 推广链接；价格与券信息以平台页面实时展示为准。
