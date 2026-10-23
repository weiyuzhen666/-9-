<script setup lang="ts">
import { onScopeDispose, computed, ref, watch } from 'vue'
import { Connection } from '@element-plus/icons-vue'
import http, { ApiError } from '../api'
import StatePanel from './StatePanel.vue'
import MoviePoster from './MoviePoster.vue'
import type { AlgorithmResult } from '../types'
import { ensureMovieTitles, getMovie, movieTitle } from '../composables/useMovieTitles'
const props = withDefaults(defineProps<{ endpoint: string | null; label: string; emptySubject?: string }>(), { emptySubject: '登录后体验' })
const loading = ref(false), error = ref<unknown>(null), unavailable = ref(false)
const result = ref<AlgorithmResult | null>(null)
let run = 0
onScopeDispose(() => { run++ })

// ----- S4: AI explanation for a single recommended movie -----
const explainVisible = ref(false), explainLoading = ref(false), explainError = ref('')
const explainData = ref<{ movie_title: string; algorithm: string; user: string; based_on: any[]; rated_titles: Record<string, string>; explanation: string; llm_status: string; note: string; evidence_sufficient: boolean } | null>(null)
// only content / itemcf expose per-item evidence today
const showExplainBtn = computed(() => !!props.endpoint && /\/(content|itemcf)$/.test(props.endpoint))
async function explainItem(movieId: string | number) {
  explainVisible.value = true
  explainLoading.value = true
  explainError.value = ''
  explainData.value = null
  try {
    const response = await http.get(`${props.endpoint}/explanation`, { params: { movie_id: String(movieId) } })
    explainData.value = response.data
  } catch (e) {
    explainError.value = '解释暂不可用'
  } finally { explainLoading.value = false }
}
function fmtContrib(v: number): string { return (v >= 0 ? '+' : '') + v.toFixed(3) }
async function load() {
  const seq = ++run
  error.value = null; result.value = null; unavailable.value = false; loading.value = false
  if (!props.endpoint) return
  loading.value = true
  try {
    const response = await http.get<AlgorithmResult>(props.endpoint)
    if (seq === run) {
      result.value = response.data
      void ensureMovieTitles(response.data.items.map(i => i.movie_id))
    }
  }
  catch (e) {
    if (seq !== run) return
    if (e instanceof ApiError && e.status === 501 && e.code === 'ALGORITHM_NOT_IMPLEMENTED') unavailable.value = true
    else error.value = e
  } finally { if (seq === run) loading.value = false }
}
watch(() => props.endpoint, load, { immediate: true })
function fmtScore(s: number | null): string {
  if (s === null || s === undefined) return ''
  return s >= 100 ? s.toFixed(0) : s >= 10 ? s.toFixed(1) : s.toFixed(2)
}
</script>
<template>
  <section class="algorithm-panel" :aria-label="label">
    <div class="section-top"><h3>{{ label }}</h3><span class="small-label">RECOMMENDATION</span></div>
    <StatePanel :loading="loading" :error="error" @retry="load">
      <div v-if="!endpoint || unavailable" class="algorithm-empty" role="status">
        <div class="algorithm-symbol"><el-icon aria-hidden="true"><Connection /></el-icon></div>
        <div><span class="status-pill">{{ !endpoint ? emptySubject : '尚未实现' }}</span><h3>{{ !endpoint ? '选择观众，开始探索' : '下一部好电影，等待算法发现' }}</h3><p>{{ !endpoint ? '先选择历史用户或登录注册账号。推荐功能等待算法接入。' : '等待算法接入；当前没有模型版本或推荐结果。' }}</p></div>
        <RouterLink v-if="!endpoint && emptySubject === '登录后体验'" class="text-link" to="/login">前往登录 →</RouterLink>
      </div>
      <div v-else-if="result" class="recommendation-results">
        <p class="model-line">模型版本 {{ result.model_version }} · {{ result.dataset_version }}</p>
        <p v-if="!result.items.length">本次没有推荐结果。</p>
        <div v-else class="rec-grid">
          <article v-for="item in result.items" :key="item.movie_id" class="rec-card">
            <RouterLink :to="`/movies/${item.movie_id}`" :aria-label="`查看 ${movieTitle(item.movie_id)} 详情`">
              <div class="rec-poster-wrap">
                <MoviePoster :path="getMovie(item.movie_id)?.poster_path" :title="movieTitle(item.movie_id)" :genres="getMovie(item.movie_id)?.genres" :year="getMovie(item.movie_id)?.release_year" :tmdbId="getMovie(item.movie_id)?.tmdb_id" />
                <span class="rec-rank">TOP {{ item.rank }}</span>
                <span v-if="item.score !== null" class="rec-score" :title="`模型分数 ${item.score}`">{{ fmtScore(item.score) }}</span>
                <span class="rec-cat">电影</span>
                <span v-if="getMovie(item.movie_id)?.release_year" class="rec-year">{{ getMovie(item.movie_id)?.release_year }}</span>
              </div>
              <h4>{{ movieTitle(item.movie_id) }}</h4>
              <p class="rec-genres">
                <span v-for="g in (getMovie(item.movie_id)?.genres || []).slice(0, 3)" :key="g" class="genre-chip">{{ g }}</span>
                <span v-if="!(getMovie(item.movie_id)?.genres || []).length" class="genre-chip genre-chip-empty">类型未收录</span>
              </p>
              <p v-if="item.recall_sources && item.recall_sources.length" class="rec-sources">召回 {{ item.recall_sources.map(s => `${s}#${item.recall_ranks?.[s] ?? '?'}`).join(' + ') }}</p>
            </RouterLink>
            <button v-if="showExplainBtn" class="explain-btn" type="button" @click="explainItem(item.movie_id)">AI解释</button>
          </article>
        </div>
      </div>
    </StatePanel>

    <el-dialog v-model="explainVisible" width="560px" class="explain-dialog" append-to-body>
      <template #header>
        <span class="explain-dialog-title">为什么推荐这部电影？</span>
      </template>
      <div v-if="explainLoading" class="explain-loading"><span class="explain-spinner" />正在生成…</div>
      <div v-else-if="explainError" class="explain-fail">{{ explainError }}，推荐列表不受影响。</div>
      <div v-else-if="explainData" class="explain-body">
        <p class="explain-meta"><strong>{{ explainData.movie_title }}</strong><span> ｜ 算法 {{ explainData.algorithm }} ｜ 历史用户 {{ explainData.user }}</span></p>
        <template v-if="explainData.evidence_sufficient">
          <p class="explain-label">真实推荐依据（来自算法本次计算）</p>
          <table class="explain-table">
            <thead><tr><th>用户评分过的电影</th><th>评分</th><th>相似度</th><th>贡献</th><th v-if="explainData.algorithm === 'content'">共同类型</th></tr></thead>
            <tbody>
              <tr v-for="row in explainData.based_on" :key="row.rated_movie_id">
                <td>{{ explainData.rated_titles[row.rated_movie_id] || row.rated_movie_id }}</td>
                <td>{{ row.rating.toFixed(1) }}</td>
                <td>{{ row.similarity.toFixed(3) }}</td>
                <td :class="row.contribution >= 0 ? 'pos' : 'neg'">{{ fmtContrib(row.contribution) }}</td>
                <td v-if="explainData.algorithm === 'content'">{{ (row.common_genres || []).join('、') || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="explainData.explanation" class="explain-ai">
            <span class="explain-ai-tag">AI 推荐理由</span>{{ explainData.explanation }}
          </p>
          <p v-else class="explain-fail">AI 解释暂不可用，以上为算法真实计算依据，推荐列表不受影响。</p>
        </template>
        <p v-else class="explain-fail">{{ explainData.note || '依据不足，无法生成个性化解释。' }}</p>
      </div>
    </el-dialog>
  </section>
</template>

<style scoped>
.model-line { color: var(--muted); font-size: 12px; margin-bottom: 14px; }
.rec-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 14px;
}
.rec-card { transition: transform 0.22s cubic-bezier(.2,.8,.3,1.2); }
.rec-card:hover { transform: translateY(-3px); }
.rec-card > a { display: block; text-decoration: none; color: inherit; }
.rec-poster-wrap { position: relative; border-radius: 10px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
.rec-card:hover .rec-poster-wrap { box-shadow: 0 8px 22px -6px rgba(0,0,0,0.18); }
.rec-poster-wrap :deep(.movie-poster) { aspect-ratio: 2/3; }
/* TOP left — rank badge (black pill) */
.rec-rank {
  position: absolute; top: 8px; left: 8px; z-index: 2;
  background: rgba(0, 0, 0, 0.72); color: #fff;
  padding: 3px 9px; border-radius: 4px;
  font-size: 11px; font-weight: 600; font-family: "SF Mono", Consolas, monospace;
  letter-spacing: 0.5px; backdrop-filter: blur(4px);
}
/* TOP right — iQiyi gold score (large) */
.rec-score {
  position: absolute; top: 4px; right: 8px; z-index: 2;
  color: #ffb400; font-size: 22px; font-weight: 800;
  font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-style: italic; letter-spacing: -0.5px;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.5), 0 0 1px rgba(0, 0, 0, 0.8);
  line-height: 1; padding: 4px 0;
}
/* BOTTOM left — category chip */
.rec-cat {
  position: absolute; bottom: 8px; left: 8px; z-index: 2;
  background: rgba(0, 0, 0, 0.65); color: #fff;
  padding: 2px 7px; border-radius: 3px;
  font-size: 10px; font-weight: 500;
  backdrop-filter: blur(4px);
}
/* BOTTOM right — release year */
.rec-year {
  position: absolute; bottom: 8px; right: 8px; z-index: 2;
  background: rgba(0, 0, 0, 0.65); color: #fff;
  padding: 2px 7px; border-radius: 3px;
  font-size: 10px; font-weight: 500; font-family: "SF Mono", Consolas, monospace;
  backdrop-filter: blur(4px);
}
.rec-card h4 {
  margin: 10px 0 6px; font-size: 14px; font-weight: 600;
  color: var(--text); line-height: 1.3;
  display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical;
  overflow: hidden;
}
.rec-card:hover h4 { color: #00BE06; }
.rec-genres { display: flex; flex-wrap: wrap; gap: 4px; min-height: 20px; }
.genre-chip {
  font-size: 10px; color: #8890a0;
  background: #f5f6f8; border: 1px solid #ecedf0;
  padding: 1px 6px; border-radius: 3px;
  line-height: 1.5;
}
.genre-chip-empty { color: #c0c4cc; }
.rec-sources {
  font-size: 10px; color: #00BE06; margin-top: 6px;
  font-family: "SF Mono", Consolas, monospace;
}
/* ----- S4 AI explanation ----- */
.explain-btn {
  margin-top: 7px; width: 100%;
  padding: 4px 0; border-radius: 999px;
  font-size: 11px; font-weight: 600; color: #00a805;
  background: rgba(0, 190, 6, .06); border: 1px solid rgba(0, 190, 6, .35);
  cursor: pointer; transition: all .2s ease;
}
.explain-btn:hover { background: #00BE06; color: #fff; }
.explain-dialog-title { font-size: 16px; font-weight: 700; color: #17421f; }
.explain-loading { display: flex; align-items: center; gap: 10px; color: #00a805; font-size: 14px; padding: 18px 0; }
.explain-spinner {
  width: 16px; height: 16px; border-radius: 50%;
  border: 2px solid rgba(0, 190, 6, .25); border-top-color: #00BE06;
  animation: explain-spin .8s linear infinite;
}
@keyframes explain-spin { to { transform: rotate(360deg); } }
.explain-meta { font-size: 14px; margin: 0 0 14px; color: #444; }
.explain-meta span { color: #888; font-size: 12.5px; }
.explain-label { font-size: 12px; font-weight: 600; color: #666; letter-spacing: .04em; margin: 0 0 8px; }
.explain-table { width: 100%; border-collapse: collapse; font-size: 12.5px; margin-bottom: 14px; }
.explain-table th, .explain-table td { border: 1px solid #e4e9ee; padding: 6px 9px; text-align: left; }
.explain-table th { background: #f3f8f4; color: #2b5c38; font-weight: 600; }
.explain-table td.pos { color: #00a805; font-weight: 600; }
.explain-table td.neg { color: #d0483e; font-weight: 600; }
.explain-ai {
  margin: 0; padding: 12px 14px; border-radius: 10px;
  background: linear-gradient(135deg, rgba(0, 190, 6, .07), rgba(0, 190, 132, .08));
  border: 1px solid rgba(0, 190, 6, .22);
  font-size: 13.5px; line-height: 1.8; color: #2c3a2f;
}
.explain-ai-tag {
  display: inline-block; margin-right: 8px; padding: 1px 9px;
  border-radius: 999px; font-size: 11px; font-weight: 700; color: #fff;
  background: linear-gradient(135deg, #00d218, #00BE06);
  vertical-align: 1px;
}
.explain-fail { margin: 0; padding: 12px 14px; border-radius: 10px; background: #fdf3f2; border: 1px solid #f3d7d3; color: #a1443a; font-size: 13px; }
</style>
