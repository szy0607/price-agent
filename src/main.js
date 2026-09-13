import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './style.css'

/**
 * v-reveal：进入视口时上移淡入（IntersectionObserver，非 scroll 监听）。
 * prefers-reduced-motion 下由 CSS 直接呈现终态。
 */
const reveal = {
  mounted(el, binding) {
    el.classList.add('reveal')
    if (binding.value) el.style.transitionDelay = `${binding.value}ms`
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add('reveal-in')
          io.disconnect()
        }
      },
      { threshold: 0.12 }
    )
    io.observe(el)
  },
}

const app = createApp(App)
app.directive('reveal', reveal)
app.use(router)
app.mount('#app')
