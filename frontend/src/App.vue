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
    <main class="app-main">
      <router-view />
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
}
.app-main {
  max-width: 480px;
  margin: 0 auto;
  min-height: calc(100vh - 50px);
}
</style>
