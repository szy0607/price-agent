<script setup>
import { computed, ref } from 'vue'

// 消费记录的「平台堆叠卡片组」：默认收拢成一摞，鼠标移入向四周散开，
// 点某张卡 = 按该平台筛选下面的记录列表。
// 分类维度取自 purchase_record.platform（该表没有 category 列，见 AGENTS.md §0）。
const props = defineProps({
  groups: { type: Array, default: () => [] }, // [{ key, count, total }]
  active: { type: String, default: null },
})
const emit = defineEmits(['select'])

const MAX_CARDS = 6

const PALETTE = [
  { bg: 'linear-gradient(150deg,#4ef08a,#2ee06a)', glyph: 'monster' }, // 亮绿
  { bg: 'linear-gradient(150deg,#2fbfe0,#17a2c8)', glyph: 'drop' },    // 湖蓝
  { bg: 'linear-gradient(150deg,#7c4dff,#5b2ad9)', glyph: 'flower' },  // 深紫
  { bg: 'linear-gradient(150deg,#ffc2d6,#ff8fb6)', glyph: 'star' },    // 浅粉
  { bg: 'linear-gradient(150deg,#ffd166,#ffb02e)', glyph: 'bolt' },    // 明黄
  { bg: 'linear-gradient(150deg,#9db4ff,#5b7cfa)', glyph: 'cloud' },   // 雾蓝
]

// 散开目标位：六个方位互不重叠地绕着底部蓝卡排。
// 蓝卡占 x[-134,134] / y[-2,150]，品牌字与贴纸排在它下半部，
// 所以这些位置一律偏上或贴两侧，只压蓝卡留白的顶边，不挡 "Yang mini+"。
// z 只用于散开后的景深（--ozd），收拢态的层级由 rank/depth 决定。
const SLOT = [
  { ox: -158, oy: -116, rot: -10, w: 152, h: 118, z: 6 },
  { ox: 150, oy: -104, rot: 8, w: 134, h: 132, z: 5 },
  { ox: -178, oy: -12, rot: 6, w: 126, h: 102, z: 4 },
  { ox: 178, oy: 34, rot: -7, w: 138, h: 98, z: 3 },
  { ox: 0, oy: -176, rot: 3, w: 122, h: 94, z: 7 },
  { ox: 196, oy: 130, rot: -6, w: 122, h: 94, z: 2 },
]

// 收拢初始位：故意互相叠压、缩小、带轻微旋转，才有「一摞」的层次感。
// 注意：收拢态的 Z 深度由下面的 depth 按排名算出，不在这里写死——
// preserve-3d 下浏览器按 3D 深度而非 z-index 排绘制顺序，深度不单调递减就会压错卡。
const STACK = [
  { sx: -14, sy: -30, s: 0.72, rot: -4 },
  { sx: 12, sy: -14, s: 0.68, rot: 5 },
  { sx: -4, sy: 2, s: 0.64, rot: -2 },
  { sx: 20, sy: 22, s: 0.7, rot: 3 },
  { sx: 0, sy: -44, s: 0.62, rot: 2 },
  { sx: -24, sy: 14, s: 0.66, rot: -6 },
]

// 平台多于 6 个时，按笔数取前 5，其余并成一张「其他平台」，避免卡片糊成一团
const placed = computed(() => {
  const sorted = [...props.groups].sort((a, b) => b.count - a.count)
  let list = sorted
  if (sorted.length > MAX_CARDS) {
    const head = sorted.slice(0, MAX_CARDS - 1)
    const tail = sorted.slice(MAX_CARDS - 1)
    list = [
      ...head,
      {
        key: '其他',
        count: tail.reduce((sum, g) => sum + g.count, 0),
        total: tail.reduce((sum, g) => sum + g.total, 0),
        merged: tail.map((g) => g.key),
      },
    ]
  }
  return list.map((group, index) => ({
    ...group,
    slot: SLOT[index % SLOT.length],
    stack: STACK[index % STACK.length],
    palette: PALETTE[index % PALETTE.length],
    // 收拢态的叠压顺序必须按笔数倒序：排第一（花钱最多）的那张要压在最上面，
    // 否则它被后面的卡挡住，鼠标根本点不到。depth 单调递减负责 3D 绘制顺序，
    // rank 负责同一深度下的兜底层级。slot.z 只管散开后的景深。
    rank: list.length - index,
    depth: 40 - index * 12,
  }))
})

// 悬停卡片的层级要顶到最高，而 CSS 无法把 z-index 动态排到最上，只能记在状态里
const hovered = ref(null)

function cardStyle(card) {
  return {
    width: `${card.slot.w}px`,
    height: `${card.slot.h}px`,
    background: card.palette.bg,
    zIndex: hovered.value === card.key ? 60 : card.rank,
    '--sx': `${card.stack.sx}px`,
    '--sy': `${card.stack.sy}px`,
    '--ss': card.stack.s,
    '--srot': `${card.stack.rot}deg`,
    '--szd': `${card.depth}px`,
    '--ox': `${card.slot.ox}px`,
    '--oy': `${card.slot.oy}px`,
    '--os': 1,
    '--orot': `${card.slot.rot}deg`,
    '--ozd': `${card.slot.z + 18}px`,
  }
}

function pick(card) {
  emit('select', card.key === props.active ? null : card.key)
}
</script>

<template>
  <div class="deck">
    <!-- 卡通形象与灯泡图标：一次定义、多处复用，不引任何外部资源 -->
    <svg width="0" height="0" class="deck__defs" aria-hidden="true" focusable="false">
      <defs>
        <symbol id="pd-monster" viewBox="0 0 40 40">
          <path d="M20 4c8.4 0 14 6 14 14v12c0 2.4-2 3.4-4 2.4l-3-1.6-3 2c-1.4.9-3.2.9-4.6 0l-2.8-1.8-3 1.8c-1.9 1.2-4.6.2-4.6-2.6V18C8 10 11.6 4 20 4z" fill="#fff" opacity=".9" />
          <circle cx="15.5" cy="17" r="2.6" fill="#172554" /><circle cx="25" cy="17" r="2.6" fill="#172554" />
          <path d="M15 24c2.8 2.6 7.4 2.6 10.2 0" stroke="#172554" stroke-width="2" fill="none" stroke-linecap="round" />
        </symbol>
        <symbol id="pd-star" viewBox="0 0 40 40">
          <path d="M20 3l4.6 10.4L36 15l-8 8.2 2.2 11.4L20 28.8 9.8 34.6 12 23.2 4 15l11.4-1.6z" fill="#fff" opacity=".92" />
        </symbol>
        <symbol id="pd-drop" viewBox="0 0 40 40">
          <path d="M20 3c6 7.6 11 12.4 11 18a11 11 0 11-22 0c0-5.6 5-10.4 11-18z" fill="#fff" opacity=".9" />
          <circle cx="16.5" cy="22" r="2.2" fill="#172554" /><circle cx="24" cy="22" r="2.2" fill="#172554" />
        </symbol>
        <symbol id="pd-flower" viewBox="0 0 40 40">
          <g fill="#fff" opacity=".9">
            <circle cx="20" cy="9" r="6.2" /><circle cx="30" cy="17" r="6.2" /><circle cx="26" cy="29" r="6.2" />
            <circle cx="14" cy="29" r="6.2" /><circle cx="10" cy="17" r="6.2" />
          </g>
          <circle cx="20" cy="20" r="4.4" fill="#172554" opacity=".85" />
        </symbol>
        <symbol id="pd-bolt" viewBox="0 0 40 40">
          <path d="M22 3L9 22h7l-3 15 15-20h-7.5z" fill="#fff" opacity=".92" />
        </symbol>
        <symbol id="pd-cloud" viewBox="0 0 40 40">
          <path d="M12 28a7 7 0 010-14 9 9 0 0117 2 6 6 0 01-1 12z" fill="#fff" opacity=".9" />
        </symbol>
        <symbol id="pd-idea" viewBox="0 0 24 24">
          <path d="M12 2a7 7 0 00-4 12.7c.6.5 1 1.2 1.1 2h5.8c.1-.8.5-1.5 1.1-2A7 7 0 0012 2z" fill="#fff" opacity=".95" />
          <rect x="9.6" y="18" width="4.8" height="1.8" rx=".9" fill="#fff" opacity=".8" />
          <rect x="10.2" y="20.6" width="3.6" height="1.6" rx=".8" fill="#fff" opacity=".6" />
        </symbol>
      </defs>
    </svg>

    <div class="deck__inner">
      <!-- 底部主视觉蓝卡：整组的视觉基底，永远在最下层、不参与散开 -->
      <div class="card card--base">
        <svg class="card__idea" aria-hidden="true"><use href="#pd-idea" /></svg>
        <div>
          <div class="card__sticker" role="img" aria-label="表情贴纸">😺✨</div>
          <div class="card__brand">Yang mini+</div>
        </div>
        <div class="card__cn">IDEA · 我的消费灵感</div>
      </div>

      <button
        v-for="card in placed"
        :key="card.key"
        type="button"
        class="card card--cat"
        :class="{ 'is-active': card.key === active }"
        :style="cardStyle(card)"
        :aria-pressed="card.key === active"
        :title="card.merged ? `其他平台：${card.merged.join('、')}` : card.key"
        @mouseenter="hovered = card.key"
        @mouseleave="hovered = null"
        @focus="hovered = card.key"
        @blur="hovered = null"
        @click="pick(card)"
      >
        <svg class="card__face" aria-hidden="true"><use :href="`#pd-${card.palette.glyph}`" /></svg>
        <div>
          <div class="card__en">{{ card.key }}</div>
          <div class="card__cn">{{ card.count }} 笔</div>
        </div>
        <div class="card__total">{{ card.total ? `¥${card.total.toLocaleString('zh-CN')}` : '价格未记' }}</div>
        <span v-if="card.key === active" class="card__badge">筛选中</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* 时长与缓动：需求区间 0.3~0.5s，ease-out 家族（快出慢收）才有漂浮感 */
.deck {
  --dur: 0.42s;
  --ease: cubic-bezier(0.16, 0.84, 0.44, 1);
  position: relative;
  width: 300px;
  height: 300px;
  perspective: 1100px; /* 3D 支点在容器上，卡片的 Z 位移才生效 */
}
.deck__defs {
  position: absolute;
}
.deck__inner {
  position: absolute;
  inset: 0;
  transform-style: preserve-3d;
  transform: rotateX(14deg) rotateZ(-6deg); /* 整组微微前倾 */
  transition: transform var(--dur) var(--ease);
}
/* 悬停 / 键盘聚焦时整组回正一点，卡片文字更好读 */
.deck:hover .deck__inner,
.deck:focus-within .deck__inner {
  transform: rotateX(6deg) rotateZ(-2deg);
}

.card {
  position: absolute;
  left: 50%;
  top: 50%;
  margin: 0;
  padding: 14px 16px;
  border: 0;
  border-radius: 26px;
  font: inherit;
  color: #fff;
  text-align: left;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  transform-origin: 50% 60%;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;

  /* 收拢态：缩小、偏淡、带旋转，叠成一摞 */
  opacity: 0.58;
  transform: translate(-50%, -50%) translate3d(var(--sx), var(--sy), var(--szd, 0px))
    scale(var(--ss, 0.74)) rotate(var(--srot, 0deg));
  box-shadow: 0 10px 22px -12px rgba(15, 23, 42, 0.38);

  /* 两套位姿都写成自定义属性，:hover 只切 transform；
     两边的函数列表逐项对齐，浏览器才能平滑插值 */
  transition: transform var(--dur) var(--ease), opacity var(--dur) var(--ease),
    box-shadow var(--dur) var(--ease);
}
.deck:hover .card,
.deck:focus-within .card {
  opacity: 1;
  transform: translate(-50%, -50%) translate3d(var(--ox), var(--oy), var(--ozd, 0px))
    scale(var(--os, 1)) rotate(var(--orot, 0deg));
}
/* 单卡悬停增强：再放大上浮一档、阴影加深、旋转摆正。
   多一层 .card:hover 选择器，优先级高于上面的散开态，因此能覆盖 */
.deck:hover .card:hover,
.deck:focus-within .card:focus-visible {
  transform: translate(-50%, -50%) translate3d(var(--ox), calc(var(--oy) - 16px), calc(var(--ozd, 0px) + 70px))
    scale(calc(var(--os, 1) * 1.09)) rotate(calc(var(--orot, 0deg) * 0.4));
  box-shadow: 0 34px 56px -20px rgba(15, 23, 42, 0.42);
}

.card__en {
  font-size: 15px;
  font-weight: 800;
  letter-spacing: 1.2px;
  text-transform: uppercase;
}
.card__cn {
  font-size: 12px;
  opacity: 0.85;
}
.card__total {
  font-size: 19px;
  font-weight: 800;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.card__face {
  position: absolute;
  /* 刻意推到角外并缩小：小卡（126px 宽）上原先 72px 的图形会压住左下的金额 */
  right: -10px;
  bottom: -10px;
  width: 54px;
  height: 54px;
  opacity: 0.85; /* 卡通形象当背景点缀，不压过文字 */
}
.card__badge {
  position: absolute;
  right: 12px;
  top: 12px;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  font-size: 10px;
  font-weight: 700;
  color: #172554;
}
.card--cat.is-active {
  box-shadow: 0 0 0 3px #fff, 0 0 0 6px rgba(37, 99, 235, 0.9);
}
.card:focus-visible {
  outline: 3px solid #fff;
  outline-offset: -6px;
}

.card--base {
  width: 268px;
  height: 152px;
  border-radius: 30px;
  background: linear-gradient(145deg, #3b82f6 0%, #2563eb 46%, #1e40af 100%);
  opacity: 1;
  z-index: 1;
  cursor: default;
  transform: translate(-50%, -50%) translate3d(0, 74px, -30px) rotate(-3deg);
  box-shadow: 0 26px 44px -22px rgba(30, 64, 175, 0.55);
}
.deck:hover .card--base,
.deck:focus-within .card--base {
  transform: translate(-50%, -50%) translate3d(0, 78px, -30px) rotate(-3deg);
}
.card__idea {
  position: absolute;
  right: 14px;
  top: 14px;
  width: 26px;
  height: 26px;
}
.card__sticker {
  font-size: 30px;
  line-height: 1;
  filter: drop-shadow(0 4px 6px rgba(0, 0, 0, 0.22));
}
.card__brand {
  font-size: 17px;
  font-weight: 800;
  letter-spacing: 0.3px;
}

@media (prefers-reduced-motion: reduce) {
  .card,
  .deck__inner {
    transition-duration: 0.01ms;
  }
}
</style>
