<script setup lang="ts">
import { onScopeDispose, ref, watch } from 'vue'
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
                <MoviePoster :path="getMovie(item.movie_id)?.poster_path" :title="movieTitle(item.movie_id)" />
                <span class="rec-rank">#{{ item.rank }}</span>
                <span v-if="item.score !== null" class="rec-score" :title="`模型分数 ${item.score}`">{{ fmtScore(item.score) }}</span>
              </div>
              <h4>{{ movieTitle(item.movie_id) }}</h4>
              <p class="rec-meta">
                {{ getMovie(item.movie_id)?.release_year || '' }}<span v-if="getMovie(item.movie_id)?.release_year && getMovie(item.movie_id)?.genres?.length"> · </span>{{ (getMovie(item.movie_id)?.genres || []).slice(0, 2).join(' / ') }}
              </p>
              <p v-if="item.recall_sources && item.recall_sources.length" class="rec-sources">召回 {{ item.recall_sources.map(s => `${s}#${item.recall_ranks?.[s] ?? '?'}`).join(' + ') }}</p>
            </RouterLink>
          </article>
        </div>
      </div>
    </StatePanel>
  </section>
</template>

<style scoped>
.model-line { color: var(--muted); font-size: 12px; margin-bottom: 14px; }
.rec-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 14px;
}
.rec-card { transition: transform 0.22s cubic-bezier(.2,.8,.3,1.2); }
.rec-card:hover { transform: translateY(-3px); }
.rec-card > a { display: block; text-decoration: none; color: inherit; }
.rec-poster-wrap { position: relative; border-radius: 8px; overflow: hidden; }
.rec-poster-wrap :deep(.movie-poster) { aspect-ratio: 2/3; }
.rec-rank {
  position: absolute; top: 6px; left: 6px; z-index: 2;
  background: rgba(0, 0, 0, 0.7); color: #fff;
  padding: 2px 8px; border-radius: 10px;
  font-size: 11px; font-weight: 600; font-family: "SF Mono", Consolas, monospace;
  backdrop-filter: blur(4px);
}
.rec-score {
  position: absolute; top: 6px; right: 6px; z-index: 2;
  background: linear-gradient(135deg, #00BE06, #00a805); color: #fff;
  padding: 3px 8px; border-radius: 10px;
  font-size: 11px; font-weight: 700; font-family: "SF Mono", Consolas, monospace;
  box-shadow: 0 2px 6px rgba(0, 190, 6, 0.4);
}
.rec-card h4 {
  margin: 8px 0 2px; font-size: 13px; font-weight: 600;
  color: var(--text); line-height: 1.3;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; min-height: 2.6em;
}
.rec-card:hover h4 { color: #00BE06; }
.rec-meta { font-size: 11px; color: var(--muted); line-height: 1.4; min-height: 1.4em; }
.rec-sources {
  font-size: 10px; color: #00BE06; margin-top: 4px;
  font-family: "SF Mono", Consolas, monospace;
}
</style>
