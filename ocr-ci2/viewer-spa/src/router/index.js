import { createRouter, createWebHistory } from 'vue-router'
import WorkbenchView from '../views/WorkbenchView.vue'
import StatsView from '../views/StatsView.vue'
import ReposView from '../views/ReposView.vue'
import RepoView from '../views/RepoView.vue'
import MrHistoryView from '../views/MrHistoryView.vue'
import SessionView from '../views/SessionView.vue'

const routes = [
  { path: '/', name: 'workbench', component: WorkbenchView },
  { path: '/stats', name: 'stats', component: StatsView },
  { path: '/repos', name: 'repos', component: ReposView },
  { path: '/r/:encodedRepo', name: 'repo', component: RepoView, props: true },
  {
    path: '/r/:encodedRepo/:sessionId',
    name: 'session',
    component: SessionView,
    props: true,
  },
  {
    path: '/mr/:projectId/:mrIid',
    name: 'mr',
    component: MrHistoryView,
    props: true,
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
