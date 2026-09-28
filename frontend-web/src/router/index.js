import { createRouter, createWebHistory } from 'vue-router'
import { refreshAuth } from '../utils/auth'

const routes = [
  { path: '/', name: 'home', component: () => import('../views/HomeView.vue'), meta: { title: '买之前，先问一句' } },
  { path: '/auth', name: 'auth', component: () => import('../views/AuthView.vue'), meta: { title: '登录' } },
  { path: '/chat', name: 'chat', component: () => import('../views/ChatView.vue'), meta: { title: '智能咨询', requiresAuth: true } },
  { path: '/compare', name: 'compare', component: () => import('../views/CompareView.vue'), meta: { title: '款式对比', requiresAuth: true } },
  { path: '/coupon', name: 'coupon', component: () => import('../views/CouponView.vue'), meta: { title: '领券指引', requiresAuth: true } },
  { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue'), meta: { title: '设置', requiresAuth: true } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('../views/NotFoundView.vue'), meta: { title: '页面不存在' } },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  // 切换路由回到顶部；浏览器前进/后退保留原位置
  scrollBehavior(to, from, savedPosition) {
    return savedPosition || { top: 0 }
  },
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 智能导购 Agent` : '智能导购 Agent'
})

router.beforeEach(async (to) => {
  if (to.meta.requiresAuth && !(await refreshAuth({ force: true }))) {
    return { name: 'auth', query: { redirect: to.fullPath } }
  }
  return true
})

export default router
