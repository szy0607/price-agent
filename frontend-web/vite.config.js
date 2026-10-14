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
      '/groups': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      // 图片两条链路都要代理到后端，前缀写 '/upload' 才能同时盖住：
      //   写 POST /upload/image、读 GET /uploads/{name}.jpg
      // 只写 '/uploads' 的话，上传请求匹配不上前缀，会被 dev server 自己 404 掉
      // （同一 URL 直连 8000 是 400，即后端路由本来好的）。
      // 后端路由里有登录+归属鉴权，cookie 随代理带过去。
      '/upload': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
