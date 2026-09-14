<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeTab = ref(0)

// 底部标签栏与路由双向同步
watch(
  () => route.path,
  (path) => {
    const map = { '/': 0, '/chat': 1, '/compare': 2, '/coupon': 3 }
    if (path in map) activeTab.value = map[path]
  },
  { immediate: true }
)
</script>

<template>
  <div class="app-shell">
    <!-- 桌面端顶部品牌标识（移动端隐藏） -->
    <div class="desktop-brand">
      <span class="desktop-brand-mark">¥</span>
      智能导购 Agent
    </div>
    <main class="app-main">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
    <van-tabbar v-model="activeTab" route fixed placeholder safe-area-inset-bottom>
      <van-tabbar-item to="/" icon="wap-home-o">首页</van-tabbar-item>
      <van-tabbar-item to="/chat" icon="chat-o">咨询</van-tabbar-item>
      <van-tabbar-item to="/compare" icon="bar-chart-o">款式对比</van-tabbar-item>
      <van-tabbar-item to="/coupon" icon="coupon-o">领券指引</van-tabbar-item>
    </van-tabbar>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  min-height: 100dvh;
}
.app-main {
  max-width: 480px;
  margin: 0 auto;
  min-height: calc(100vh - 50px);
  min-height: calc(100dvh - 50px);
}
.page-enter-active,
.page-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.page-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

/* ---------- 桌面端：底部标签栏转为顶部导航 ---------- */

.desktop-brand {
  display: none;
}

@media (min-width: 768px) {
  .app-main {
    max-width: 1080px;
    padding-top: 56px;
    min-height: calc(100dvh - 56px);
  }

  .desktop-brand {
    position: fixed;
    top: 0;
    left: 28px;
    height: 56px;
    display: flex;
    align-items: center;
    gap: 9px;
    font-size: 16px;
    font-weight: 800;
    letter-spacing: -0.3px;
    color: var(--ink);
    z-index: 9;
    pointer-events: none;
  }
  .desktop-brand-mark {
    width: 26px;
    height: 26px;
    border-radius: 8px;
    background: linear-gradient(160deg, #16295e, #3e66e0);
    color: #fff;
    font-size: 14px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .app-shell :deep(.van-tabbar--fixed) {
    top: 0;
    bottom: auto;
    left: 0;
    right: 0;
    height: 56px;
    max-width: 1080px;
    margin: 0 auto;
    border-bottom: 1px solid var(--line);
    box-shadow: 0 6px 20px -14px rgba(23, 32, 56, 0.18);
  }
  .app-shell :deep(.van-tabbar) {
    justify-content: center;
    gap: 6px;
  }
  .app-shell :deep(.van-tabbar-item) {
    flex: 0 0 auto;
    flex-direction: row;
    gap: 6px;
    padding: 0 20px;
    font-size: 14px;
    cursor: pointer;
  }
  .app-shell :deep(.van-tabbar-item--active) {
    background: var(--brand-light);
    border-radius: 999px;
  }
  /* 占位元素只服务于移动端底部固定模式 */
  .app-shell :deep(.van-tabbar--placeholder) {
    display: none;
  }
}
</style>
