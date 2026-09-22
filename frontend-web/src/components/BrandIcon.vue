<script setup>
/**
 * 品牌吉祥物图标（依据「项目图标设计」绘制）：
 * 深蓝礼帽 + 深蓝西装 + 白衬衫领带 + 手持放大镜（内含 ¥），扁平化风格。
 * 主题色与站点 accent（#2563eb）一致，任意尺寸下保持清晰。
 */
defineProps({
  size: { type: [Number, String], default: 24 },
})
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 48 48"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <!-- 礼帽帽冠 -->
    <rect x="14" y="2" width="20" height="11" rx="2.5" fill="#2563eb" />
    <!-- 帽带 -->
    <rect x="14" y="8" width="20" height="3.2" fill="#1d4ed8" />
    <!-- 帽檐 -->
    <rect x="8" y="12.5" width="32" height="4" rx="2" fill="#2563eb" />
    <!-- 脸 -->
    <circle cx="24" cy="21" r="6" fill="#ffd9b3" />
    <!-- 西装 -->
    <path
      d="M24 28 C17 28 11 32.5 11 43 L11 46 L37 46 L37 43 C37 32.5 31 28 24 28 Z"
      fill="#2563eb"
    />
    <!-- 白衬衫领口 -->
    <path d="M24 28 L19.5 33.5 L28.5 33.5 Z" fill="#ffffff" />
    <!-- 领带 -->
    <path d="M24 33.5 L21.2 36.8 L22 42 L24 43.2 L26 42 L26.8 36.8 Z" fill="#1d4ed8" />
    <!-- 放大镜镜片 -->
    <circle cx="32.5" cy="35" r="8" fill="#dbeafe" stroke="#2563eb" stroke-width="2.5" />
    <!-- 放大镜手柄 -->
    <line x1="37.8" y1="40.3" x2="43" y2="45.5" stroke="#2563eb" stroke-width="3.2" stroke-linecap="round" />
    <!-- ¥ 符号 -->
    <path d="M32.5 30.8 L29.7 34 M32.5 30.8 L35.3 34" stroke="#ffffff" stroke-width="1.9" stroke-linecap="round" />
    <path d="M32.5 34 L32.5 39.2" stroke="#ffffff" stroke-width="1.9" stroke-linecap="round" />
    <line x1="30" y1="35.8" x2="35" y2="35.8" stroke="#ffffff" stroke-width="1.9" stroke-linecap="round" />
    <line x1="30" y1="37.9" x2="35" y2="37.9" stroke="#ffffff" stroke-width="1.9" stroke-linecap="round" />
  </svg>
</template>
