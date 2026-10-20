<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'
import http, { ApiError } from '../api'
import { useRemote } from '../composables/useRemote'
import type { Algorithm, HistoryUser, Movie, Page } from '../types'
import StatePanel from '../components/StatePanel.vue'
import PageNav from '../components/PageNav.vue'
import AlgorithmPanel from '../components/AlgorithmPanel.vue'
const route = useRoute(), router = useRouter(), auth = useAuth()
const source = ref('ml'), algorithm = ref('content'), selected = ref('')
const userPage = ref(1), users = useRemote<Page<HistoryUser>>(), ratings = useRemote<Page<Movie>>()
const ratingPage = ref(1), available = ref<Algorithm[]>([]), registryError = ref<unknown>(null)
const algorithmGroups = computed(() => [
  { label: '核心算法 · 学生实现', items: available.value.filter(a => ['content', 'itemcf', 'als'].includes(a.algorithm)) },
  { label: '配套策略 · 热门与冷启动', items: available.value.filter(a => ['popular', 'cold_start'].includes(a.algorithm)) },
])
const evaluationError = ref<unknown>(null), evaluationPending = ref(false), evaluationMissing = ref(false)
// 冷启动向导：当前账号评分数与偏好类型，用于展示冷启动策略阶段
const myRatings = ref<{ total: number; genres: string[] }>({ total: 0, genres: [] })
const myRatingsPending = ref(false), wizardKey = ref(0)
const showColdStartWizard = computed(() => source.value === 'app' && algorithm.value === 'cold_start' && !!auth.account)
async function fetchMyRatings() {
  if (!auth.account) { myRatings.value = { total: 0, genres: [] }; return }
  myRatingsPending.value = true
  try {
    const res = await http.get<Page<Movie>>('/ratings', { params: { page: 1, per_page: 50 } })
    const genreCount: Record<string, number> = {}
    for (const it of res.data.items) for (const g of it.genres || []) genreCount[g] = (genreCount[g] || 0) + 1
    myRatings.value = { total: res.data.total, genres: Object.entries(genreCount).sort((a, b) => b[1] - a[1]).slice(0, 3).map(e => e[0]) }
  } finally { myRatingsPending.value = false }
}
function refreshWizard() { void fetchMyRatings().then(() => { wizardKey.value++ }) }
watch(() => [source.value, algorithm.value, auth.account?.subject_key], () => { if (source.value === 'app') void fetchMyRatings() }, { immediate: true })
const subject = computed(() => source.value === 'ml' ? (selected.value ? `ml:${selected.value}` : '') : auth.account?.subject_key || '')
const endpoint = computed(() => !subject.value ? null : source.value === 'ml' ? `/demo/history-users/${selected.value}/recommendations/${algorithm.value}` : `/me/recommendations/${algorithm.value}`)
function updateUrl() { void router.replace({ path:'/experiments', query:{ source:source.value, algorithm:algorithm.value, ...(selected.value ? {user:selected.value} : {}) } }) }
async function fetchUsers(page = userPage.value) { userPage.value = page; await users.load(async () => (await http.get<Page<HistoryUser>>('/demo/history-users',{params:{page,per_page:20}})).data) }
function fetchRatings() { if (source.value !== 'ml' || !selected.value) return; return ratings.load(async () => (await http.get<Page<Movie>>(`/demo/history-users/${encodeURIComponent(selected.value)}/ratings`,{params:{page:ratingPage.value,per_page:10}})).data) }
async function fetchRegistry() { try { available.value=(await http.get<{items:Algorithm[]}>('/experiments/algorithms')).data.items; registryError.value=null } catch(e) { registryError.value=e } }
async function fetchEvaluation() { evaluationPending.value=true; evaluationError.value=null; evaluationMissing.value=false; try { await http.get('/experiments/evaluations') } catch(e) { if(e instanceof ApiError && e.status===501 && e.code==='EVALUATION_NOT_IMPLEMENTED') evaluationMissing.value=true; else evaluationError.value=e } finally { evaluationPending.value=false } }
watch(() => route.query, () => { source.value=route.query.source==='app'?'app':'ml'; algorithm.value=typeof route.query.algorithm==='string' && /^[a-z_]+$/.test(route.query.algorithm) ? route.query.algorithm:'content'; selected.value=typeof route.query.user==='string' && /^[1-9][0-9]*$/.test(route.query.user)?route.query.user:'' }, {immediate:true})
watch(() => [selected.value,source.value], () => {ratingPage.value=1; void fetchRatings()})
void fetchUsers(); void fetchRegistry(); void fetchEvaluation(); void fetchRatings()
</script>
<template>
  <div class="page"><div class="page-heading"><p class="eyebrow">RECOMMENDATION LAB</p><h1>推荐实验室<span class="heading-dot">.</span></h1><p>从一位观众的历史出发，探索不同算法的推荐结果。</p></div><div class="lab-notice"><span class="status-pill">课程实验</span><p>历史用户只读；注册账号与匿名用户相互隔离。当前推荐与离线评价算法均等待接入。</p></div>
    <div class="lab-layout"><aside class="lab-controls"><h2>实验设置</h2><label for="subject-source">用户来源</label><el-select id="subject-source" v-model="source" @change="updateUrl"><el-option label="MovieLens 历史用户（只读）" value="ml" /><el-option label="当前注册账号" value="app" /></el-select><template v-if="source==='ml'"><label for="history-user">选择历史用户</label><el-select id="history-user" v-model="selected" placeholder="请从真实用户列表选择" @change="updateUrl"><el-option v-for="u in users.data.value?.items" :key="u.ml_user_id" :label="`${u.subject_key} · ${u.evaluation_role}`" :value="u.ml_user_id" /></el-select><StatePanel v-if="users.error.value" :error="users.error.value" @retry="fetchUsers()" /><p v-if="users.loading.value" class="muted" role="status">正在加载用户…</p><div class="user-pager"><el-button :disabled="userPage===1 || users.loading.value" @click="fetchUsers(userPage-1)">上一组</el-button><span>{{ userPage }} / {{ Math.ceil((users.data.value?.total || 0)/20) || 1 }}</span><el-button :disabled="!users.data.value || userPage*20>=users.data.value.total || users.loading.value" @click="fetchUsers(userPage+1)">下一组</el-button></div><p class="form-hint">按原始用户ID分页，支持全部课堂历史用户。</p></template><div v-else class="current-subject"><p>{{ auth.account?.login_name || '请先登录注册账号' }}</p><span>{{ auth.account?.subject_key || '尚未登录' }}</span><RouterLink v-if="!auth.account" to="/login" class="text-link">前往登录 →</RouterLink></div><label for="algorithm-select">推荐算法</label><el-select id="algorithm-select" v-model="algorithm" @change="updateUrl"><el-option-group v-for="group in algorithmGroups" :key="group.label" :label="group.label"><el-option v-for="a in group.items" :key="a.algorithm" :label="a.algorithm" :value="a.algorithm" /></el-option-group></el-select><div class="algorithm-scope"><p><strong>学生实现的三种核心算法</strong>内容推荐（content）、ItemCF、Spark ALS。</p><p><strong>配套推荐策略</strong>热门（popular）、新用户冷启动（cold_start）；同样保留未实现状态。</p></div><StatePanel v-if="registryError" :error="registryError" @retry="fetchRegistry" /><div class="model-info"><span>当前对象</span><strong>{{ subject || '未选择' }}</strong><span>模型版本</span><strong>等待算法接入</strong><span>运行模式</span><strong>business · 只读实验入口</strong></div></aside>
    <div class="lab-results"><section v-if="showColdStartWizard" class="coldstart-wizard" aria-label="新用户冷启动向导"><div class="section-top"><h2>新用户冷启动向导</h2><span class="status-pill">{{ myRatings.total ? '策略：热门 + 内容混合（个性化）' : '策略：热门榜单（非个性化）' }}</span></div><p v-if="!myRatings.total">你还没有评分。当前 cold_start 返回的是<strong>全局热门榜单</strong>，并非个性化结果。去电影库给 1 部电影评分，推荐会立即融入你的类型偏好。</p><template v-else><p>已基于你的 <strong>{{ myRatings.total }}</strong> 条评分实现个性化：内容信号权重 β = min(0.7, 0.1×{{ myRatings.total }}) = <strong>{{ Math.min(0.7, 0.1 * myRatings.total).toFixed(1) }}</strong>，热门权重 α = {{ (1 - Math.min(0.7, 0.1 * myRatings.total)).toFixed(1) }}。</p><p v-if="myRatings.genres.length">从你的评分中提取的偏好类型：<strong>{{ myRatings.genres.join(' / ') }}</strong></p><p class="muted">再评几部电影，个性化权重会继续提升（上限 0.7）。评分或收藏后点击下方按钮即可看到推荐变化。</p></template><div class="wizard-actions"><RouterLink class="text-link" to="/movies">去电影库评分 →</RouterLink><RouterLink class="text-link" to="/profile">查看我的评分与收藏 →</RouterLink><el-button size="small" :loading="myRatingsPending" @click="refreshWizard">我已评分，刷新推荐</el-button></div></section><AlgorithmPanel :key="wizardKey" :label="`${algorithm} · 推荐结果`" :endpoint="endpoint" :empty-subject="source==='ml' ? '请选择历史用户' : '登录后体验'" /><section v-if="source==='ml'" class="history-panel"><div class="section-top"><h2>历史评分</h2><span class="status-pill">{{ subject || '未选择用户' }} · 只读</span></div><StatePanel :loading="ratings.loading.value" :error="ratings.error.value" :empty="!selected || !!ratings.data.value && !ratings.data.value.items.length" title="选择一位历史观众" description="这里将显示真实历史评分，不提供修改入口。" @retry="fetchRatings"><div class="table-scroll"><el-table :data="ratings.data.value?.items || []" aria-label="历史用户只读评分表"><el-table-column label="电影" min-width="200"><template #default="scope"><RouterLink :to="`/movies/${scope.row.movie_id}`" class="text-link">{{ scope.row.movielens_title }}</RouterLink></template></el-table-column><el-table-column prop="movie_id" label="电影ID" width="100" /><el-table-column prop="rating" label="历史评分" width="100" /></el-table></div><PageNav :page="ratingPage" :size="10" :total="ratings.data.value?.total || 0" @change="ratingPage=$event;fetchRatings()" /></StatePanel></section><section class="evaluation-panel"><div class="section-top"><h2>离线评价</h2><span class="small-label">PRECISION@10 / RECALL@10</span></div><StatePanel :loading="evaluationPending" :error="evaluationError" @retry="fetchEvaluation"><div class="evaluation-empty"><span class="status-pill">{{ evaluationMissing ? '尚未实现' : '等待接入' }}</span><p>暂无评价指标，等待离线评价程序接入。</p><small>训练仅允许使用固定 train；此页面不连接 evaluation 数据库。</small></div></StatePanel></section></div></div>
  </div>
</template>

<style scoped>
.algorithm-scope { margin-top: 14px; color: var(--muted); font-size: 12px; line-height: 1.8; }
.algorithm-scope p + p { margin-top: 10px; }
.algorithm-scope strong { display: block; color: var(--text); font-weight: 500; }
.coldstart-wizard { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; margin-bottom: 18px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.04); }
.coldstart-wizard p { color: var(--muted); font-size: 13px; line-height: 1.8; margin-top: 8px; }
.coldstart-wizard p strong { color: var(--text); font-weight: 600; }
.wizard-actions { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
</style>
