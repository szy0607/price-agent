import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'home', component: () => import('../views/HomeView.vue'), meta: { title: '买之前，先问一句' } },
  { path: '/chat', name: 'chat', component: () => import('../views/ChatView.vue'), meta: { title: '智能咨询' } },
  { path: '/compare', name: 'compare', component: () => import('../views/CompareView.vue'), meta: { title: '款式对比' } },
  { path: '/coupon', name: 'coupon', component: () => import('../views/CouponView.vue'), meta: { title: '领券指引' } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 智能导购 Agent` : '智能导购 Agent'
})

export default router
