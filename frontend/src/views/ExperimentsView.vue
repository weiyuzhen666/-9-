<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuth } from '../stores/auth'
import { ElMessage } from 'element-plus'
import http, { ApiError, errorMessage } from '../api'
import { useRemote } from '../composables/useRemote'
import type { Algorithm, HistoryUser, Movie, Page } from '../types'
import StatePanel from '../components/StatePanel.vue'
import PageNav from '../components/PageNav.vue'
import AlgorithmPanel from '../components/AlgorithmPanel.vue'
import { ensureMovieTitles, movieTitle } from '../composables/useMovieTitles'
const route = useRoute(), router = useRouter(), auth = useAuth()
const source = ref('ml'), algorithm = ref('content'), selected = ref('')
const userPage = ref(1), users = useRemote<Page<HistoryUser>>(), ratings = useRemote<Page<Movie>>()
const ratingPage = ref(1), available = ref<Algorithm[]>([]), registryError = ref<unknown>(null)
const algorithmGroups = computed(() => [
  { label: '核心算法 · 学生实现', items: available.value.filter(a => ['content', 'itemcf', 'als'].includes(a.algorithm)) },
  { label: '配套策略 · 热门与冷启动', items: available.value.filter(a => ['popular', 'cold_start'].includes(a.algorithm)) },
  { label: '扩展算法 · 加权RRF融合', items: available.value.filter(a => ['rrf_fusion'].includes(a.algorithm)) },
])
const evaluationError = ref<unknown>(null), evaluationPending = ref(false), evaluationMissing = ref(false)
interface EvalMetric { user_count: number; avg_precision_at_10: number; avg_recall_at_10: number; empty_results: number }
interface EvalMetrics { validation?: Record<string, EvalMetric>; test?: Record<string, EvalMetric> }
const evaluationMetrics = ref<EvalMetrics | null>(null)
const EVAL_ALGO_ORDER = ['content', 'itemcf', 'als', 'popular', 'cold_start']
const EVAL_PARTS: Array<'test' | 'validation'> = ['test', 'validation']
function evalRows(part: 'test' | 'validation'): Array<{ algo: string; metric: EvalMetric; bestP: boolean; bestR: boolean }> {
  const bucket = evaluationMetrics.value?.[part]
  if (!bucket) return []
  const rows = EVAL_ALGO_ORDER.filter(algo => bucket[algo]).map(algo => ({ algo, metric: bucket[algo] }))
  if (!rows.length) return []
  const maxP = Math.max(...rows.map(r => r.metric.avg_precision_at_10))
  const maxR = Math.max(...rows.map(r => r.metric.avg_recall_at_10))
  return rows.map(r => ({ algo: r.algo, metric: r.metric, bestP: r.metric.avg_precision_at_10 === maxP, bestR: r.metric.avg_recall_at_10 === maxR }))
}
// 智能助手（S2：LLM 工具调用）
interface AssistantToolCall { name: string; arguments: Record<string, unknown>; result: any }
interface AssistantResult { answer: string; parser: string; generated_by: string; tool_calls: AssistantToolCall[] }
const assistantQuery = ref(''), assistantResult = ref<AssistantResult | null>(null), assistantPending = ref(false)
async function runAssistant() {
  const q = assistantQuery.value.trim(); if (!q) return
  assistantPending.value = true; assistantResult.value = null
  try {
    const res = await http.get<AssistantResult>('/assistant/query', { params: { q } })
    assistantResult.value = res.data
    const ids = res.data.tool_calls.filter(tc => tc.name === 'recommend_movies' && tc.result?.items)
      .flatMap(tc => (tc.result.items as { movie_id: string }[]).map(i => i.movie_id))
    if (ids.length) void ensureMovieTitles(ids)
  }
  catch (e) { ElMessage.error(errorMessage(e)) }
  finally { assistantPending.value = false }
}
// 冷启动向导：当前账号评分数与偏好类型，用于展示冷启动策略阶段
const myRatings = ref<{ total: number; genres: string[] }>({ total: 0, genres: [] })
const myRatingsPending = ref(false), wizardKey = ref(0)
const showColdStartWizard = computed(() => source.value === 'app' && algorithm.value === 'cold_start' && !!auth.account)
// 英文 genre → 中文，用于向导显示
const EN_TO_ZH = {
  'Action':'动作','Adventure':'冒险','Animation':'动画','Children':'儿童','Comedy':'喜剧',
  'Crime':'犯罪','Documentary':'纪录','Drama':'剧情','Fantasy':'奇幻','Film-Noir':'黑色电影',
  'Horror':'恐怖','Musical':'歌舞','Mystery':'悬疑','Romance':'爱情','Sci-Fi':'科幻',
  'Thriller':'惊悚','War':'战争','Western':'西部',
} as const
function toZh(genres: string[] | null | undefined): string[] { return (genres || []).map(g => EN_TO_ZH[g as keyof typeof EN_TO_ZH] || g) }
const myFavoriteGenresZh = computed(() => toZh(auth.account?.favorite_genres))
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
async function fetchEvaluation() { evaluationPending.value=true; evaluationError.value=null; evaluationMissing.value=false; evaluationMetrics.value=null; try { const res = await http.get<{status:string; metrics:EvalMetrics|null}>('/experiments/evaluations'); if (res.data.metrics) evaluationMetrics.value = res.data.metrics; else evaluationMissing.value = true } catch(e) { if(e instanceof ApiError && e.status===501 && e.code==='EVALUATION_NOT_IMPLEMENTED') evaluationMissing.value=true; else evaluationError.value=e } finally { evaluationPending.value=false } }
watch(() => route.query, () => { source.value=route.query.source==='app'?'app':'ml'; algorithm.value=typeof route.query.algorithm==='string' && /^[a-z_]+$/.test(route.query.algorithm) ? route.query.algorithm:'content'; selected.value=typeof route.query.user==='string' && /^[1-9][0-9]*$/.test(route.query.user)?route.query.user:'' }, {immediate:true})
watch(() => [selected.value,source.value], () => {ratingPage.value=1; void fetchRatings()})
void fetchUsers(); void fetchRegistry(); void fetchEvaluation(); void fetchRatings()
</script>
<template>
  <div class="page"><div class="page-heading"><p class="eyebrow">RECOMMENDATION LAB</p><h1>推荐实验室<span class="heading-dot">.</span></h1><p>从一位观众的历史出发，探索不同算法的推荐结果。</p></div><div class="lab-notice"><span class="status-pill">课程实验</span><p>历史用户只读；注册账号与匿名用户相互隔离。当前推荐与离线评价算法均等待接入。</p></div>
    <div class="lab-layout"><aside class="lab-controls"><h2>实验设置</h2><label for="subject-source">用户来源</label><el-select id="subject-source" v-model="source" @change="updateUrl"><el-option label="MovieLens 历史用户（只读）" value="ml" /><el-option label="当前注册账号" value="app" /></el-select><template v-if="source==='ml'"><label for="history-user">选择历史用户</label><el-select id="history-user" v-model="selected" placeholder="请从真实用户列表选择" @change="updateUrl"><el-option v-for="u in users.data.value?.items" :key="u.ml_user_id" :label="`${u.subject_key} · ${u.evaluation_role}`" :value="u.ml_user_id" /></el-select><StatePanel v-if="users.error.value" :error="users.error.value" @retry="fetchUsers()" /><p v-if="users.loading.value" class="muted" role="status">正在加载用户…</p><div class="user-pager"><el-button :disabled="userPage===1 || users.loading.value" @click="fetchUsers(userPage-1)">上一组</el-button><span>{{ userPage }} / {{ Math.ceil((users.data.value?.total || 0)/20) || 1 }}</span><el-button :disabled="!users.data.value || userPage*20>=users.data.value.total || users.loading.value" @click="fetchUsers(userPage+1)">下一组</el-button></div><p class="form-hint">按原始用户ID分页，支持全部课堂历史用户。</p></template><div v-else class="current-subject"><p>{{ auth.account?.login_name || '请先登录注册账号' }}</p><span>{{ auth.account?.subject_key || '尚未登录' }}</span><RouterLink v-if="!auth.account" to="/login" class="text-link">前往登录 →</RouterLink></div><label for="algorithm-select">推荐算法</label><el-select id="algorithm-select" v-model="algorithm" @change="updateUrl"><el-option-group v-for="group in algorithmGroups" :key="group.label" :label="group.label"><el-option v-for="a in group.items" :key="a.algorithm" :label="a.algorithm" :value="a.algorithm" /></el-option-group></el-select><div class="algorithm-scope"><p><strong>学生实现的三种核心算法</strong>内容推荐（content）、ItemCF、Spark ALS。</p><p><strong>配套推荐策略</strong>热门（popular）、新用户冷启动（cold_start）。</p><p><strong>扩展算法</strong>加权RRF融合（rrf_fusion）：融合多路候选名次，可查看每部电影的召回来源与原始名次。</p></div><div class="algorithm-quick"><span class="quick-label">算法快速切换：</span><div class="quick-chips"><button v-for="a in available" :key="a.algorithm" type="button" class="quick-chip" :class="{active: algorithm===a.algorithm}" @click="algorithm=a.algorithm; updateUrl()">{{ a.algorithm }}</button></div></div><StatePanel v-if="registryError" :error="registryError" @retry="fetchRegistry" /><div class="model-info"><span>当前对象</span><strong>{{ subject || '未选择' }}</strong><span>模型版本</span><strong>等待算法接入</strong><span>运行模式</span><strong>business · 只读实验入口</strong></div></aside>
    <div class="lab-results"><section v-if="showColdStartWizard" class="coldstart-wizard" aria-label="新用户冷启动向导"><div class="section-top"><h2>新用户冷启动向导</h2><span class="status-pill">{{ myRatings.total ? '策略：热门 + 内容混合（个性化）' : (auth.account?.favorite_genres?.length ? '策略：热门 + 类型偏好融合（半个性化）' : '策略：热门榜单（非个性化）') }}</span></div><p v-if="!myRatings.total && !auth.account?.favorite_genres?.length">你还没有评分，也没有在注册时选择电影类型。当前 cold_start 返回的是<strong>全局热门榜单</strong>。去电影库给 1 部电影评分，或在个人中心更新你的类型偏好，推荐会立即融入个性化信号。</p><p v-else-if="!myRatings.total && auth.account?.favorite_genres?.length">你还没有评分，但注册时选择了：<strong>{{ myFavoriteGenresZh.join(' / ') }}</strong>。当前 cold_start 已经将<strong>热门榜单</strong>与你的<strong>类型偏好</strong>融合（α=0.5，β=0.5）。去电影库给电影评分后，推荐会进一步融入内容信号。</p><template v-else><p>已基于你的 <strong>{{ myRatings.total }}</strong> 条评分实现个性化：内容信号权重 β = min(0.7, 0.1×{{ myRatings.total }}) = <strong>{{ Math.min(0.7, 0.1 * myRatings.total).toFixed(1) }}</strong>，热门权重 α = {{ (1 - Math.min(0.7, 0.1 * myRatings.total)).toFixed(1) }}。</p><p v-if="myRatings.genres.length">从你的评分中提取的偏好类型：<strong>{{ toZh(myRatings.genres).join(' / ') }}</strong></p><p class="muted">再评几部电影，个性化权重会继续提升（上限 0.7）。评分或收藏后点击下方按钮即可看到推荐变化。</p></template><div class="wizard-actions"><RouterLink class="text-link" to="/movies">去电影库评分 →</RouterLink><RouterLink class="text-link" to="/profile">查看我的评分与收藏 →</RouterLink><el-button size="small" :loading="myRatingsPending" @click="refreshWizard">我已评分，刷新推荐</el-button></div></section><section class="assistant-panel" aria-label="智能助手"><div class="section-top"><h2>智能助手 · LLM 工具调用</h2><span v-if="assistantResult" class="status-pill">{{ assistantResult.generated_by }}</span><span v-else class="status-pill">输入问题体验真实工具调用</span></div><p class="form-hint">例如：“推荐几部科幻片”、“搜索阿甘正传”、“热门电影有哪些”</p><div class="assistant-input"><el-input v-model="assistantQuery" placeholder="输入你的问题…" clearable maxlength="200" show-word-limit @keyup.enter="runAssistant" /><el-button type="primary" :loading="assistantPending" :disabled="!assistantQuery.trim()" @click="runAssistant">提问</el-button></div><div v-if="assistantPending" class="muted" role="status">正在调用工具生成回答…</div><div v-if="assistantResult" class="assistant-answer"><p><strong>回答：</strong>{{ assistantResult.answer }}</p><p class="muted" style="margin-top:8px">解析器：{{ assistantResult.parser }}；实际调用的工具：<span v-for="(tc,i) in assistantResult.tool_calls" :key="i">{{ i ? '、' : '' }}{{ tc.name }}（{{ tc.result.items ? tc.result.items.length + '条' : (tc.result.length + '部') }}）</span></p><div v-for="(tc,i) in assistantResult.tool_calls" :key="i" class="tool-call-block"><h4>{{ tc.name }}</h4><p v-if="tc.name==='search_movies'" class="muted">参数：{{ JSON.stringify(tc.arguments) }}</p><ol v-if="tc.name==='search_movies' && tc.result.length"><li v-for="m in tc.result" :key="m.movie_id"><RouterLink :to="`/movies/${m.movie_id}`">{{ m.title_zh || m.movielens_title }}</RouterLink> · {{ m.genres.join(' / ') }} · {{ m.release_year }}</li></ol><p v-if="tc.name==='recommend_movies'" class="muted">参数：{{ JSON.stringify(tc.arguments) }} → {{ tc.result.model_version }}</p><ol v-if="tc.name==='recommend_movies' && tc.result.items"><li v-for="it in tc.result.items" :key="it.movie_id"><RouterLink :to="`/movies/${it.movie_id}`">{{ movieTitle(it.movie_id) }}</RouterLink> · 排名 {{ it.rank }}<span v-if="it.recall_sources"> · 召回来源 {{ it.recall_sources.join(' + ') }}</span></li></ol></div></div></section><AlgorithmPanel :key="wizardKey" :label="`${algorithm} · 推荐结果`" :endpoint="endpoint" :empty-subject="source==='ml' ? '请选择历史用户' : '登录后体验'" /><section v-if="source==='ml'" class="history-panel"><div class="section-top"><h2>历史评分</h2><span class="status-pill">{{ subject || '未选择用户' }} · 只读</span></div><StatePanel :loading="ratings.loading.value" :error="ratings.error.value" :empty="!selected || !!ratings.data.value && !ratings.data.value.items.length" title="选择一位历史观众" description="这里将显示真实历史评分，不提供修改入口。" @retry="fetchRatings"><div class="table-scroll"><el-table :data="ratings.data.value?.items || []" aria-label="历史用户只读评分表"><el-table-column label="电影" min-width="200"><template #default="scope"><RouterLink :to="`/movies/${scope.row.movie_id}`" class="text-link">{{ scope.row.movielens_title }}</RouterLink></template></el-table-column><el-table-column prop="movie_id" label="电影ID" width="100" /><el-table-column prop="rating" label="历史评分" width="100" /></el-table></div><PageNav :page="ratingPage" :size="10" :total="ratings.data.value?.total || 0" @change="ratingPage=$event;fetchRatings()" /></StatePanel></section><section class="evaluation-panel"><div class="section-top"><h2>离线评价</h2><span class="small-label">PRECISION@10 / RECALL@10</span></div><StatePanel :loading="evaluationPending" :error="evaluationError" @retry="fetchEvaluation"><div v-if="evaluationMetrics" class="evaluation-table-wrap"><div v-for="part in EVAL_PARTS" :key="part" class="eval-part"><h3>{{ part === 'test' ? 'Test 分区（最终报告）' : 'Validation 分区（调参检查）' }}</h3><table class="eval-table"><thead><tr><th>算法</th><th>有效用户</th><th>Precision@10</th><th>Recall@10</th><th>空结果</th></tr></thead><tbody><tr v-for="row in evalRows(part)" :key="part + '-' + row.algo"><td><strong>{{ row.algo }}</strong></td><td class="num">{{ row.metric.user_count }}</td><td class="num" :class="{best: row.bestP}">{{ row.metric.avg_precision_at_10.toFixed(5) }}</td><td class="num" :class="{best: row.bestR}">{{ row.metric.avg_recall_at_10.toFixed(5) }}</td><td class="num">{{ row.metric.empty_results }}</td></tr></tbody></table></div><p class="eval-note">数据来源：<code>models/evaluation/metrics.json</code>，由 <code>recommender/student/evaluate_all.py</code> 在冻结 train.csv 上真实计算，未做手工修饰。</p></div><div v-else class="evaluation-empty"><span class="status-pill">{{ evaluationMissing ? '尚未实现' : '等待接入' }}</span><p>暂无评价指标，等待离线评价程序接入。</p><small>训练仅允许使用固定 train；此页面不连接 evaluation 数据库。</small></div></StatePanel></section></div></div>
  </div>
</template>

<style scoped>
.evaluation-table-wrap { display: grid; gap: 22px; }
.eval-part h3 { font-size: 14px; margin: 0 0 10px; color: var(--text); font-weight: 600; }
.eval-part h3::before { content: "●"; color: #00BE06; margin-right: 6px; font-size: 10px; }
.eval-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.eval-table th { background: #f8f9fb; color: #555; font-weight: 600; text-align: left; padding: 10px 14px; border-bottom: 2px solid #e8e9ec; font-size: 12px; }
.eval-table td { padding: 10px 14px; border-bottom: 1px solid #f0f1f3; }
.eval-table tbody tr:hover { background: #f8fff5; }
.eval-table .num { font-family: "SF Mono", Consolas, monospace; font-size: 12px; }
.eval-table .best { color: #00BE06; font-weight: 700; }
.eval-note { color: var(--muted); font-size: 12px; line-height: 1.7; }
.eval-note code { background: #f5f6f8; padding: 1px 6px; border-radius: 3px; font-family: "SF Mono", Consolas, monospace; font-size: 11px; }
.algorithm-scope { margin-top: 14px; color: var(--muted); font-size: 12px; line-height: 1.8; }
.algorithm-scope p + p { margin-top: 10px; }
.algorithm-scope strong { display: block; color: var(--text); font-weight: 500; }
.algorithm-quick { margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--border); }
.algorithm-quick .quick-label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 8px; }
.algorithm-quick .quick-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.algorithm-quick .quick-chip {
  padding: 5px 12px; border-radius: 14px; font-size: 12px; font-family: "SF Mono", Consolas, monospace;
  background: #f5f6f8; color: #555; border: 1px solid #e8e9ec; cursor: pointer;
  transition: all 0.18s ease;
}
.algorithm-quick .quick-chip:hover { background: rgba(0,190,6,0.08); color: #00BE06; border-color: rgba(0,190,6,0.3); }
.algorithm-quick .quick-chip.active {
  background: #00BE06; color: #fff; border-color: #00BE06; font-weight: 600;
  box-shadow: 0 2px 8px -2px rgba(0,190,6,0.5);
}
.coldstart-wizard { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; margin-bottom: 18px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.04); }
.coldstart-wizard p { color: var(--muted); font-size: 13px; line-height: 1.8; margin-top: 8px; }
.coldstart-wizard p strong { color: var(--text); font-weight: 600; }
.wizard-actions { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; margin-top: 12px; }
.assistant-panel { background: var(--surface); border: 1px solid var(--border); border-radius: 14px; padding: 16px 18px; margin-bottom: 18px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.04); }
.assistant-input { display: flex; gap: 10px; margin-top: 10px; }
.assistant-input .el-input { flex: 1; }
.assistant-answer { margin-top: 12px; border-top: 1px solid var(--border); padding-top: 12px; }
.assistant-answer > p { font-size: 13px; line-height: 1.8; }
.tool-call-block { background: var(--bg); border-radius: 10px; padding: 10px 12px; margin-top: 10px; }
.tool-call-block h4 { font-size: 13px; margin-bottom: 4px; color: var(--accent); }
.tool-call-block ol { margin: 6px 0 0 18px; font-size: 13px; line-height: 1.9; }
.tool-call-block ol li a { color: var(--accent); }
</style>
