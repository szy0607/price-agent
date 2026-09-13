<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { couponTypes, couponSteps, platformBenefits, products, PLATFORMS } from '../mock/data'

const route = useRoute()

// 默认淘宝；若从商品卡跳转而来（带 id），定位到该商品所属平台
const fromProduct = products.find((p) => p.id === route.query.id)
const activePlat = ref(fromProduct ? fromProduct.platform : 'taobao')

const platName = computed(() => PLATFORMS[activePlat.value].name)
const steps = computed(() => couponSteps[activePlat.value])
const benefits = computed(() => platformBenefits.filter((b) => b.platform === activePlat.value))

const platTabs = [
  { key: 'taobao', label: '淘宝' },
  { key: 'jd', label: '京东' },
  { key: 'pdd', label: '拼多多' },
]
</script>

<template>
  <div class="page">
    <h1 class="page-title">领券指引</h1>
    <p class="page-subtitle">
      我们不提供推广链接——这里只告诉你券的类型、限制和领取步骤，由你自己领券、自己下单，价格透明不误导。
    </p>

    <!-- 券类型说明 -->
    <section class="card">
      <div class="card-title">🎟️ 两种券，两种口径</div>
      <div v-for="t in couponTypes" :key="t.key" class="ctype" :style="{ borderLeftColor: t.color }">
        <div class="ctype-name">{{ t.name }}</div>
        <div class="ctype-desc">{{ t.desc }}</div>
        <div class="ctype-rule">处理方式：{{ t.rule }}</div>
      </div>
      <div class="dual-price-note">
        <div><span class="price-a">价格 A（公开价）</span>：不领券直接买的价格，人人可得。</div>
        <div><span class="price-b">价格 B（领券价）</span>：领到券后的价格；渠道专享券需通过专属渠道领取，领不到就按 A 价买。</div>
      </div>
    </section>

    <!-- 平台领券步骤 -->
    <section class="card">
      <div class="card-title">🧭 领券步骤 · {{ platName }}</div>
      <van-tabs v-model:active="activePlat" shrink>
        <van-tab v-for="t in platTabs" :key="t.key" :title="t.label" :name="t.key" />
      </van-tabs>
      <van-steps direction="vertical" :active="steps.length" active-color="var(--brand)" class="steps">
        <van-step v-for="(s, i) in steps" :key="i">
          <b class="step-title">第 {{ i + 1 }} 步</b>
          <div class="step-desc">{{ s }}</div>
        </van-step>
      </van-steps>
    </section>

    <!-- 优惠类型获取策略 -->
    <section class="card">
      <div class="card-title">📡 {{ platName }}优惠类型怎么获取</div>
      <div v-for="b in benefits" :key="b.name" class="benefit-row">
        <div class="benefit-name">
          <van-tag :type="b.viaApi ? 'primary' : 'default'">{{ b.viaApi ? 'API 实时' : 'RAG 指引' }}</van-tag>
          {{ b.name }}
        </div>
        <div class="benefit-how">{{ b.how }}</div>
      </div>
      <p class="benefit-note">
        商品属性型优惠（券 / 满减 / PLUS 价 / 百亿补贴）走联盟 API 实时查询；
        账号 / 流量型权益（淘金币、天降红包、限时折扣等千人千面权益）不参与价格计算，只做规则指引。
      </p>
    </section>

    <!-- 不做什么 -->
    <section class="card no-list">
      <div class="card-title">🚫 我们不做什么</div>
      <div class="no-item">不代下单、不代支付——交易 100% 由你完成</div>
      <div class="no-item">不提供 CPS 推广链接——只给领券路径</div>
      <div class="no-item">不用评论区数据——评论晒单滞后且被刷单污染，对「当前能否领到券」无参考价值</div>
      <div class="no-item">不承诺千人千面权益——天降红包、限时折扣以页面实时为准</div>
    </section>

    <p class="disclaimer">
      券的面额、门槛、有效期与余量以平台实时数据为准；本指引不构成价格承诺。
    </p>
  </div>
</template>

<style scoped>
.ctype {
  border-left: 3px solid;
  background: var(--bg);
  border-radius: 0 10px 10px 0;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.ctype-name {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 3px;
}
.ctype-desc {
  font-size: 12px;
  color: var(--ink-2);
  line-height: 1.6;
}
.ctype-rule {
  font-size: 11px;
  color: var(--brand-deep);
  margin-top: 4px;
  line-height: 1.5;
}
.dual-price-note {
  font-size: 12px;
  line-height: 1.8;
  background: #f6f9ff;
  border-radius: 10px;
  padding: 10px 12px;
}
.steps {
  margin-top: 14px;
}
.step-title {
  font-size: 13px;
}
.step-desc {
  font-size: 12px;
  color: var(--ink-2);
  line-height: 1.6;
  margin-top: 2px;
}
.benefit-row {
  padding: 8px 0;
  border-bottom: 1px dashed var(--line);
}
.benefit-row:last-of-type {
  border-bottom: none;
}
.benefit-name {
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
}
.benefit-how {
  font-size: 11px;
  color: var(--ink-2);
  padding-left: 2px;
}
.benefit-note {
  font-size: 11px;
  color: var(--ink-3);
  line-height: 1.7;
  margin: 10px 0 0;
}
.no-list {
  background: #fff8f7;
}
.no-item {
  font-size: 12px;
  line-height: 1.9;
  color: #8a4a44;
}
.no-item::before {
  content: '✕ ';
  font-weight: 700;
}
</style>
