import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'home', component: () => import('../views/HomeView.vue'), meta: { title: '首页' } },
  { path: '/chat', name: 'chat', component: () => import('../views/ChatView.vue'), meta: { title: '咨询' } },
  { path: '/compare', name: 'compare', component: () => import('../views/CompareView.vue'), meta: { title: '款式对比' } },
  { path: '/coupon', name: 'coupon', component: () => import('../views/CouponGuideView.vue'), meta: { title: '领券指引' } },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.afterEach((to) => {
  const base = '智能导购 Agent'
  document.title = to.meta.title ? `${to.meta.title} · ${base}` : base
})

export default router
