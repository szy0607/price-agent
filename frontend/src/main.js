import { createApp } from 'vue'
import Vant from 'vant'
import 'vant/lib/index.css'
import App from './App.vue'
import router from './router'
import './styles/main.css'

const app = createApp(App)
app.use(router)
app.use(Vant)
app.mount('#app')
