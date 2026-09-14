<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="page nf rise">
    <div class="nf-mark">🧭</div>
    <h1 class="nf-title">页面不存在</h1>
    <p class="nf-desc">这个页面可能已被移动，或者链接不完整。</p>
    <van-button type="primary" round block @click="router.replace('/')">回到首页</van-button>
  </div>
</template>

<style scoped>
.nf {
  min-height: 60vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 0 32px;
}
.nf-mark {
  font-size: 44px;
  margin-bottom: 12px;
}
.nf-title {
  font-size: 20px;
  font-weight: 700;
  margin: 0 0 6px;
}
.nf-desc {
  font-size: 13px;
  color: var(--ink-2);
  line-height: 1.6;
  margin: 0 0 20px;
}
</style>
