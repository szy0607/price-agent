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
  { step: '①', title: '咨询', desc: '发商品链接或提问' },
  { step: '②', title: '款式对比', desc: '采集各款式信息与差异' },
  { step: '③', title: '双价测算', desc: '公开价 / 领券价一目了然' },
  { step: '④', title: '领券指引', desc: '自己领券，最低价拿下' },
]

const samples = ['三款降噪耳机怎么选？', '750ml 保温杯哪款划算？', '氨基酸洗面奶单支还是两支装？']
</script>

<template>
  <div class="page home">
    <!-- Hero -->
    <section class="hero card">
      <div class="hero-badge">网页版 Demo</div>
      <h1 class="hero-title">智能导购 Agent</h1>
      <p class="hero-desc">
        多款式不知道怎么选？Agent 帮你对比款式、测算活动价格，
        告诉你<b>怎么领券拿到最低价</b>——下单这一步，交给你自己。
      </p>
      <van-button type="primary" round block size="large" @click="router.push('/chat')">
        开始咨询
      </van-button>
    </section>

    <!-- 核心原则 -->
    <div class="section-label">核心原则</div>
    <section class="principles">
      <div v-for="p in principles" :key="p.title" class="card principle">
        <van-icon :name="p.icon" size="20" color="var(--brand)" />
        <div>
          <div class="principle-title">{{ p.title }}</div>
          <div class="principle-desc">{{ p.desc }}</div>
        </div>
      </div>
    </section>

    <!-- 四步闭环 -->
    <div class="section-label">咨询四步闭环</div>
    <section class="card">
      <div class="flow">
        <div v-for="(f, i) in flow" :key="f.step" class="flow-item">
          <div class="flow-step">{{ f.step }}</div>
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
    <section class="card">
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
.hero {
  background: linear-gradient(135deg, #3b7cff 0%, #6f5bff 100%);
  color: #fff;
  border: none;
  padding: 22px 16px;
}
.hero-badge {
  display: inline-block;
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.2);
  margin-bottom: 10px;
}
.hero-title {
  margin: 0 0 8px;
  font-size: 24px;
}
.hero-desc {
  font-size: 13px;
  line-height: 1.7;
  margin: 0 0 16px;
  opacity: 0.92;
}
.principles {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.principle {
  margin: 0;
  padding: 12px;
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
.flow {
  display: flex;
  justify-content: space-between;
  text-align: center;
}
.flow-step {
  font-size: 18px;
  margin-bottom: 4px;
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
.sample {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 13px 14px;
  cursor: pointer;
  font-size: 13px;
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
</style>
