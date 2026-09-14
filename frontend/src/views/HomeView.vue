<script setup>
import { useRouter } from 'vue-router'
import { apiContract } from '../mock/data'

const router = useRouter()

const principles = [
  { icon: 'shield-o', title: 'AI 是顾问，不是代购', desc: '不碰登录态、不碰支付、不碰资金' },
  { icon: 'eye-o', title: '双价透明', desc: '公开价 / 领券价同时展示，领不到的券明确说明' },
  { icon: 'link-o', title: '不提供推广链接', desc: '领券步骤自己走，交易 100% 由你完成' },
  { icon: 'apps-o', title: '官方数据源', desc: '联盟查券 API 实时查询，不做任何采集爬取' },
]

const flow = [
  { title: '咨询', desc: '发商品链接或提问' },
  { title: '款式对比', desc: '采集各款式信息与差异' },
  { title: '双价测算', desc: '公开价 / 领券价一目了然' },
  { title: '领券指引', desc: '自己领券，最低价拿下' },
]

const samples = ['三款降噪耳机怎么选？', '750ml 保温杯哪款划算？', '氨基酸洗面奶单支还是两支装？']
</script>

<template>
  <div class="page home">
    <!-- Hero -->
    <section class="hero rise">
      <div class="hero-inner">
        <div class="hero-badge">网页版 Demo</div>
        <h1 class="hero-title">智能导购 Agent</h1>
        <p class="hero-desc">
          多款式不知道怎么选？Agent 帮你对比款式、测算活动价格，
          告诉你<b>怎么领券拿到最低价</b>——下单这一步，交给你自己。
        </p>
        <van-button class="hero-cta" size="large" round @click="router.push('/chat')">
          开始咨询
        </van-button>
      </div>
    </section>

    <!-- 核心原则 -->
    <div class="section-label">核心原则</div>
    <section class="principles">
      <div v-for="p in principles" :key="p.title" class="card principle">
        <div class="principle-icon">
          <van-icon :name="p.icon" size="18" color="var(--brand)" />
        </div>
        <div>
          <div class="principle-title">{{ p.title }}</div>
          <div class="principle-desc">{{ p.desc }}</div>
        </div>
      </div>
    </section>

    <!-- 四步闭环 -->
    <div class="section-label">咨询四步闭环</div>
    <section class="card rise d2">
      <div class="flow">
        <div v-for="(f, i) in flow" :key="f.title" class="flow-item">
          <div class="flow-dot">{{ i + 1 }}</div>
          <div class="flow-title">{{ f.title }}</div>
          <div class="flow-desc">{{ f.desc }}</div>
        </div>
      </div>
    </section>

    <!-- 试试这样问 -->
    <div class="section-label">试试这样问</div>
    <section class="samples">
      <div
        v-for="s in samples"
        :key="s"
        class="card sample"
        @click="router.push({ path: '/chat', query: { q: s } })"
      >
        <span>{{ s }}</span>
        <van-icon name="arrow" color="var(--ink-3)" />
      </div>
    </section>

    <!-- 数据接口说明 -->
    <div class="section-label">数据说明</div>
    <section class="card rise d5">
      <div class="card-title">📊 联盟查券 API · 统一适配层</div>
      <div v-for="a in apiContract" :key="a.fn" class="api-row">
        <code>{{ a.fn }}</code>
        <span>{{ a.desc }}</span>
      </div>
      <p class="api-note">Demo 阶段由本地 Mock 数据源模拟返回；正式版接入淘宝联盟 / 京东联盟 / 多多进宝查券接口。</p>
    </section>

    <p class="disclaimer">
      本工具仅提供信息聚合与决策建议，不代下单、不代支付；价格与券信息以平台页面实时展示为准。
    </p>
  </div>
</template>

<style scoped>
/* Hero：深海军蓝底 + 品牌蓝径向光晕 + 噪点，替代紫蓝 AI 渐变 */
.hero {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-lg);
  padding: 24px 16px 20px;
  margin-bottom: 12px;
  color: #fff;
  background: linear-gradient(165deg, #101d44 0%, #16295e 55%, #1b3170 100%);
  box-shadow: 0 16px 36px -18px rgba(16, 29, 68, 0.55);
}
.hero::before {
  content: '';
  position: absolute;
  inset: 0;
  background:
    radial-gradient(110% 80% at 88% -12%, rgba(88, 133, 255, 0.5), transparent 62%),
    radial-gradient(80% 60% at -8% 112%, rgba(62, 102, 224, 0.35), transparent 58%);
  pointer-events: none;
}
.hero::after {
  content: '';
  position: absolute;
  inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)'/%3E%3C/svg%3E");
  opacity: 0.05;
  pointer-events: none;
}
.hero-inner {
  position: relative;
  z-index: 1;
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  letter-spacing: 1px;
  padding: 3px 10px;
  border-radius: 999px;
  color: rgba(255, 255, 255, 0.92);
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.22);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  margin-bottom: 12px;
}
.hero-title {
  margin: 0 0 8px;
  font-size: 27px;
  font-weight: 800;
  letter-spacing: -0.5px;
  line-height: 1.2;
  text-wrap: balance;
}
.hero-desc {
  font-size: 13px;
  line-height: 1.75;
  margin: 0 0 18px;
  color: rgba(233, 239, 255, 0.88);
}
.hero-desc b {
  color: #fff;
}
.hero-cta {
  background: #fff;
  color: var(--ink);
  border: 0;
  font-weight: 600;
  box-shadow: 0 10px 24px -10px rgba(6, 13, 35, 0.6);
}
.hero-cta:active {
  transform: scale(0.98);
}

/* 核心原则：图标芯片 + 逐个入场 */
.principles {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.principle {
  margin: 0;
  padding: 12px;
  animation: rise 0.45s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}
.principle:nth-child(1) { animation-delay: 0.08s; }
.principle:nth-child(2) { animation-delay: 0.14s; }
.principle:nth-child(3) { animation-delay: 0.2s; }
.principle:nth-child(4) { animation-delay: 0.26s; }
.principle-icon {
  width: 34px;
  height: 34px;
  border-radius: var(--radius-sm);
  background: var(--brand-light);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 8px;
}
.principle-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 3px;
}
.principle-desc {
  font-size: 11px;
  color: var(--ink-2);
  line-height: 1.5;
}

/* 四步闭环：圆点 + 虚线连接线，终点强调 */
.flow {
  position: relative;
  display: flex;
  justify-content: space-between;
  padding-top: 4px;
}
.flow::before {
  content: '';
  position: absolute;
  top: 18px;
  left: 14%;
  right: 14%;
  border-top: 2px dashed var(--line);
}
.flow-item {
  position: relative;
  z-index: 1;
  text-align: center;
}
.flow-dot {
  width: 28px;
  height: 28px;
  margin: 0 auto 6px;
  border-radius: 50%;
  background: #fff;
  border: 2px solid var(--brand-light);
  color: var(--brand-deep);
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.flow-item:last-child .flow-dot {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
  box-shadow: 0 4px 12px -4px rgba(62, 102, 224, 0.6);
}
.flow-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 2px;
}
.flow-desc {
  font-size: 10px;
  color: var(--ink-2);
  max-width: 72px;
  margin: 0 auto;
  line-height: 1.4;
}

/* 示例问题：按压反馈 + 逐个入场 */
.samples .sample {
  animation: rise 0.45s cubic-bezier(0.22, 0.61, 0.36, 1) both;
}
.samples .sample:nth-child(1) { animation-delay: 0.3s; }
.samples .sample:nth-child(2) { animation-delay: 0.36s; }
.samples .sample:nth-child(3) { animation-delay: 0.42s; }
.sample {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 13px 14px;
  cursor: pointer;
  font-size: 13px;
  transition: transform 0.18s cubic-bezier(0.22, 0.61, 0.36, 1), background-color 0.18s ease;
}
.sample:active {
  transform: scale(0.98);
  background: #f7f9fd;
}
.sample .van-icon {
  transition: transform 0.18s ease;
}
.sample:active .van-icon {
  transform: translateX(2px);
}

.api-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 7px 0;
  border-bottom: 1px dashed var(--line);
  font-size: 12px;
}
.api-row:last-of-type {
  border-bottom: none;
}
.api-row code {
  font-size: 11px;
  background: var(--brand-light);
  color: var(--brand-deep);
  padding: 2px 6px;
  border-radius: 6px;
}
.api-note {
  font-size: 11px;
  color: var(--ink-3);
  margin: 10px 0 0;
  line-height: 1.6;
}

@media (prefers-reduced-motion: reduce) {
  .principle,
  .samples .sample {
    animation: none;
  }
}

/* ---------- 桌面端 ---------- */

.sample:hover {
  border-color: rgba(62, 102, 224, 0.35);
}
.sample:hover .van-icon {
  transform: translateX(2px);
  color: var(--brand);
}

@media (min-width: 768px) {
  .hero {
    padding: 44px 40px 40px;
  }
  .hero-title {
    font-size: 36px;
  }
  .hero-desc {
    font-size: 15px;
    max-width: 560px;
    margin-bottom: 22px;
  }
  .hero-cta {
    max-width: 280px;
  }
  .principles {
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
  }
  .principle {
    padding: 16px;
  }
  .principle-desc {
    font-size: 12px;
  }
  .flow {
    max-width: 720px;
    margin: 0 auto;
  }
  .flow-desc {
    max-width: 130px;
    font-size: 12px;
  }
  .samples {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }
  .samples .sample {
    margin-bottom: 0;
    padding: 15px 18px;
    font-size: 14px;
  }
  .api-row {
    font-size: 13px;
  }
  .api-row code {
    font-size: 12px;
  }
  .api-note {
    font-size: 12px;
  }
}

</style>
