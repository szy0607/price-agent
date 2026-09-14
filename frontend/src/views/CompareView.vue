<script setup>
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { products, PLATFORMS } from '../mock/data'

const route = useRoute()
const activeIdx = ref(0)

// 从商品卡深链跳转（/compare?id=xxx）时定位到对应商品
onMounted(() => {
  const idx = products.findIndex((p) => p.id === route.query.id)
  if (idx > -1) activeIdx.value = idx
})

const product = computed(() => products[activeIdx.value])
const platform = computed(() => PLATFORMS[product.value.platform])

// 领券价 B 最低的款式
const cheapestSku = computed(() =>
  product.value.skus.reduce((acc, s) => (s.priceB < acc.priceB ? s : acc), product.value.skus[0])
)

// 规格行 = 所有 SKU 规格键的并集
const specKeys = computed(() => {
  const keys = []
  product.value.skus.forEach((s) => {
    Object.keys(s.specs).forEach((k) => {
      if (!keys.includes(k)) keys.push(k)
    })
  })
  return keys
})
</script>

<template>
  <div class="page">
    <h1 class="page-title">款式对比</h1>
    <p class="page-subtitle">
      款式信息由联盟查券 API 采集，规格参数结合 RAG 规格库补全；价格为实时双价口径。
    </p>

    <!-- 品类切换 -->
    <van-tabs v-model:active="activeIdx" shrink swipeable background="transparent">
      <van-tab v-for="p in products" :key="p.id" :title="`${p.emoji} ${p.category}`" />
    </van-tabs>

    <!-- 商品头 -->
    <section class="card prod-head rise">
      <div class="prod-emoji">{{ product.emoji }}</div>
      <div>
        <div class="prod-title">{{ product.title }}</div>
        <div class="prod-meta">
          <span class="tag-soft" :style="{ color: platform.color, background: platform.color + '14' }">
            {{ platform.name }}
          </span>
          <span class="prod-sales">{{ product.sales }}</span>
        </div>
        <div class="prod-intro">{{ product.intro }}</div>
      </div>
    </section>

    <!-- 双价矩阵 -->
    <section class="card rise d1">
      <div class="card-title">💰 双价测算矩阵</div>
      <div class="price-grid">
        <div class="price-grid-head">
          <span>款式</span>
          <span>公开价 A</span>
          <span>领券价 B</span>
        </div>
        <div
          v-for="s in product.skus"
          :key="s.name"
          class="price-grid-row"
          :class="{ best: s === cheapestSku }"
        >
          <span class="row-name">
            {{ s.name }}
            <em v-if="s.subsidy" class="subsidy">百亿补贴</em>
            <em v-if="s === cheapestSku" class="best-tag">到手最低</em>
          </span>
          <span class="price-a">¥{{ s.priceA }}</span>
          <span class="price-b">¥{{ s.priceB }}</span>
        </div>
      </div>
      <p class="legend">
        A = 直接购买价；B = 领到券后的价格。渠道专享券存在「能否领到」两种情况，两个价格都已给出。
      </p>
    </section>

    <!-- 规格对比表 -->
    <section class="card rise d2">
      <div class="card-title">🔍 规格参数对比</div>
      <div class="spec-table-wrap">
        <table class="spec-table">
          <thead>
            <tr>
              <th>参数</th>
              <th v-for="s in product.skus" :key="s.name">{{ s.name }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="k in specKeys" :key="k">
              <td class="spec-key">{{ k }}</td>
              <td v-for="s in product.skus" :key="s.name">{{ s.specs[k] || '—' }}</td>
            </tr>
            <tr>
              <td class="spec-key">库存</td>
              <td v-for="s in product.skus" :key="s.name">{{ s.stock }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 券信息明细 -->
    <section class="card rise d3">
      <div class="card-title">🎟️ 券信息明细</div>
      <div v-for="s in product.skus" :key="s.name" class="coupon-line">
        <div class="coupon-line-head">
          <b>{{ s.name }}</b>
          <van-tag :type="s.coupon.type === 'public' ? 'success' : 'warning'">
            {{ s.coupon.type === 'public' ? '公开券' : '渠道专享券' }}
          </van-tag>
        </div>
        <div class="coupon-line-body">
          {{ s.coupon.name }}：{{ s.coupon.threshold ? `满 ${s.coupon.threshold} 减` : '立减' }} {{ s.coupon.amount }} 元 · {{ s.coupon.note }}
        </div>
        <div v-if="s.promotion && s.promotion !== '—'" class="coupon-promo">促销：{{ s.promotion }}</div>
      </div>
    </section>

    <!-- 结论 -->
    <section class="card conclusion rise d4">
      <div class="card-title">✅ 对比结论（A5 推荐引导 Agent）</div>
      <p>{{ product.conclusion }}</p>
    </section>

    <p class="disclaimer">
      以上为信息聚合与决策建议，不构成交易行为；券的有效期、余量与最终到手价以平台页面实时展示为准。
    </p>
  </div>
</template>

<style scoped>
.prod-head {
  display: flex;
  gap: 12px;
}
.prod-emoji {
  font-size: 34px;
  width: 60px;
  height: 60px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  border-radius: 12px;
  border: 1px solid var(--line);
}
.prod-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 5px;
}
.prod-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
}
.prod-sales {
  font-size: 11px;
  color: var(--ink-3);
}
.prod-intro {
  font-size: 12px;
  color: var(--ink-2);
  line-height: 1.6;
}
.price-grid {
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.price-grid-head,
.price-grid-row {
  display: grid;
  grid-template-columns: 1.6fr 1fr 1fr;
  padding: 9px 12px;
  font-size: 13px;
  text-align: right;
  border-bottom: 1px solid var(--line);
}
.price-grid-head {
  background: var(--bg);
  font-size: 11px;
  color: var(--ink-2);
}
.price-grid-row:last-child {
  border-bottom: none;
}
.price-grid-row.best {
  background: #f1faf5;
}
.row-name {
  text-align: left;
  font-size: 12px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 3px;
}
.row-name em.subsidy {
  font-style: normal;
  font-size: 9px;
  color: #d2372c;
  border: 1px solid rgba(210, 55, 44, 0.45);
  border-radius: 4px;
  padding: 0 3px;
}
.row-name em.best-tag {
  font-style: normal;
  font-size: 9px;
  color: #fff;
  background: var(--price-b);
  border-radius: 4px;
  padding: 1px 4px;
}
.legend {
  font-size: 11px;
  color: var(--ink-3);
  line-height: 1.6;
  margin: 10px 0 0;
}
.spec-table-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.spec-table {
  border-collapse: collapse;
  font-size: 12px;
  min-width: 100%;
}
.spec-table th,
.spec-table td {
  border: 1px solid var(--line);
  padding: 7px 10px;
  text-align: left;
  white-space: nowrap;
}
.spec-table th {
  background: var(--bg);
  font-weight: 600;
}
.spec-key {
  color: var(--ink-2);
  background: #fafbfd;
}
.coupon-line {
  padding: 9px 0;
  border-bottom: 1px dashed var(--line);
}
.coupon-line:last-child {
  border-bottom: none;
  padding-bottom: 0;
}
.coupon-line-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  margin-bottom: 4px;
}
.coupon-line-body {
  font-size: 12px;
  color: var(--ink-2);
  line-height: 1.6;
}
.coupon-promo {
  font-size: 11px;
  color: var(--brand-deep);
  margin-top: 3px;
}
.conclusion p {
  font-size: 13px;
  line-height: 1.8;
  margin: 0;
}

/* ---------- 桌面端：内容限宽居中，表格放大 ---------- */

@media (min-width: 768px) {
  .page {
    max-width: 920px;
    margin: 0 auto;
  }
  .price-grid-head,
  .price-grid-row {
    font-size: 14px;
    padding: 11px 14px;
  }
  .row-name {
    font-size: 13px;
  }
  .spec-table {
    font-size: 13px;
  }
  .spec-table th,
  .spec-table td {
    padding: 9px 12px;
  }
}

</style>
