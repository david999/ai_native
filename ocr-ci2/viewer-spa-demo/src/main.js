import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import Workbench from './views/Workbench.vue'
import ReviewDetail from './views/ReviewDetail.vue'

const routes = [
  { path: '/', component: Workbench },
  { path: '/review/:jobId', component: ReviewDetail, props: true },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

createApp(App).use(router).mount('#app')
