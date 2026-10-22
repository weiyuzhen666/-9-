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
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 16px;
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
</style>
