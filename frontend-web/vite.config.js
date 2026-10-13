import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  base: '/price-agent/',
  server: {
    host: true,
    port: 5174,
    proxy: {
      '/auth': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/setting': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/chat': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/purchase-records': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/cart': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/items': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // 用户上传的商品图：/uploads/{name}.jpg 必须代理到后端，否则 dev server 自己 404，
      // 前端 <img @error> 会兜底成占位图。后端路由里有登录+归属鉴权，cookie 随代理带过去。
      '/uploads': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
