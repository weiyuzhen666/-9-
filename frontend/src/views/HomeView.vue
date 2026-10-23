<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowRight, Search, Reading, ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import http from '../api'
import { useAuth } from '../stores/auth'
import { useRemote } from '../composables/useRemote'
import type { Movie, Page } from '../types'
import MovieCard from '../components/MovieCard.vue'
import MoviePoster from '../components/MoviePoster.vue'
import StatePanel from '../components/StatePanel.vue'
import AlgorithmPanel from '../components/AlgorithmPanel.vue'
const auth = useAuth()
const { data, error, loading, load } = useRemote<Page<Movie>>()
const fetchMovies = () => load(async () => (await http.get<Page<Movie>>('/movies', { params: { per_page: 10 } })).data)
onMounted(fetchMovies)

// ----- 顶部影院风轮播：取片库前 6 部做焦点展示 -----
const featuredRemote = useRemote<Page<Movie>>()
const fetchFeatured = () => featuredRemote.load(async () => (await http.get<Page<Movie>>('/movies', { params: { per_page: 6 } })).data)
onMounted(fetchFeatured)
const featured = computed(() => featuredRemote.data.value?.items || [])
// 轮播氛围背景：本地真实海报优先，TMDb CDN 兜底，均失败则保留深色渐变
function bgStyle(m: Movie) {
  const layers: string[] = []
  if (m.tmdb_id) layers.push(`url("/api/v1/posters/movie_${m.tmdb_id}.jpg")`)
  if (m.poster_path && /^\/[\w.-]+\.(jpg|jpeg|png|webp)$/i.test(m.poster_path)) layers.push(`url("https://image.tmdb.org/t/p/w780${m.poster_path}")`)
  return layers.length ? { backgroundImage: layers.join(', ') } : {}
}
function clip(text: string | null | undefined, n = 96): string {
  if (!text) return '真实片库成员，等待你的评分与收藏。点开它，让每一次观影留下回响。'
  return text.length > n ? text.slice(0, n) + '…' : text
}

// ----- 全类型快捷入口（提交英文 genre，界面显示中文，每类专属配色；默认折叠只显示热门） -----
const allGenres = [
  { zh: '动作', en: 'Action', c: '#ff5b3a', hot: true },
  { zh: '喜剧', en: 'Comedy', c: '#f0a020', hot: true },
  { zh: '科幻', en: 'Sci-Fi', c: '#2f7bff', hot: true },
  { zh: '爱情', en: 'Romance', c: '#ff4d8d', hot: true },
  { zh: '动画', en: 'Animation', c: '#8a5cf6', hot: true },
  { zh: '悬疑', en: 'Mystery', c: '#5468e8', hot: true },
  { zh: '冒险', en: 'Adventure', c: '#2e9e5b' },
  { zh: '儿童', en: 'Children', c: '#ff9f2e' },
  { zh: '犯罪', en: 'Crime', c: '#3b5bdb' },
  { zh: '纪录', en: 'Documentary', c: '#9c7c2e' },
  { zh: '剧情', en: 'Drama', c: '#6470d8' },
  { zh: '奇幻', en: 'Fantasy', c: '#a04de8' },
  { zh: '黑色电影', en: 'Film-Noir', c: '#5a6270' },
  { zh: '恐怖', en: 'Horror', c: '#c2255c' },
  { zh: '歌舞', en: 'Musical', c: '#e63fa8' },
  { zh: '惊悚', en: 'Thriller', c: '#e64545' },
  { zh: '战争', en: 'War', c: '#7a6c3e' },
  { zh: '西部', en: 'Western', c: '#c77b2e' },
  { zh: 'IMAX', en: 'IMAX', c: '#2ea3a8' },
]
const genresExpanded = ref(false)
const visibleGenres = computed(() => genresExpanded.value ? allGenres : allGenres.filter(g => g.hot))

// ----- 轮播高度随屏宽自适应 -----
const carouselHeight = ref('440px')
function syncHeight() { carouselHeight.value = window.innerWidth < 640 ? '560px' : window.innerWidth < 1100 ? '400px' : '440px' }
onMounted(() => { syncHeight(); window.addEventListener('resize', syncHeight) })
onBeforeUnmount(() => window.removeEventListener('resize', syncHeight))
</script>
<template>
  <div class="page home-page">
    <section class="hero-carousel">
      <el-carousel v-if="featured.length" :interval="5200" arrow="hover" :height="carouselHeight" class="fc-carousel">
        <el-carousel-item v-for="(m, i) in featured" :key="m.movie_id">
          <div class="fc-slide">
            <div class="fc-bg" :style="bgStyle(m)" aria-hidden="true" />
            <span class="fc-index" aria-hidden="true">{{ String(i + 1).padStart(2, '0') }}</span>
            <span class="fc-side" aria-hidden="true">CINELAB PRESENTS</span>
            <span class="fc-counter" aria-hidden="true">{{ String(i + 1).padStart(2, '0') }} / {{ String(featured.length).padStart(2, '0') }}</span>
            <div class="fc-inner">
              <div class="fc-copy">
                <p class="fc-eyebrow"><span class="fc-dot" />本周焦点 · FEATURED</p>
                <h2 class="fc-title">{{ m.title_zh || m.movielens_title }}</h2>
                <p class="fc-meta">{{ m.release_year || '年份未收录' }} · #{{ m.movie_id }}</p>
                <div class="fc-chips"><span v-for="g in m.genres.slice(0, 3)" :key="g" class="fc-chip">{{ g }}</span></div>
                <p class="fc-overview">{{ clip(m.overview) }}</p>
                <div class="fc-actions">
                  <RouterLink class="fc-btn-primary" :to="`/movies/${m.movie_id}`">▶ 立即查看</RouterLink>
                  <RouterLink class="fc-btn-ghost" to="/movies">浏览全部 <el-icon aria-hidden="true"><ArrowRight /></el-icon></RouterLink>
                </div>
              </div>
              <RouterLink class="fc-poster" :to="`/movies/${m.movie_id}`" aria-hidden="true" tabindex="-1">
                <MoviePoster :path="m.poster_path" :title="m.movielens_title" :genres="m.genres" :year="m.release_year" :tmdbId="m.tmdb_id" />
              </RouterLink>
            </div>
          </div>
        </el-carousel-item>
      </el-carousel>
      <div v-else class="fc-fallback"><StatePanel :loading="featuredRemote.loading.value" :error="featuredRemote.error.value" @retry="fetchFeatured" /></div>
    </section>

    <div class="genre-strip" :class="{ expanded: genresExpanded }"><span class="genre-strip-label">类型速览</span><RouterLink v-for="t in visibleGenres" :key="t.en" class="genre-chip-link" :style="{ '--gc': t.c }" :to="{ path: '/movies', query: { genre: t.en } }">{{ t.zh }}</RouterLink><button type="button" class="genre-toggle" @click="genresExpanded = !genresExpanded">{{ genresExpanded ? '收起' : `全部 ${allGenres.length} 类` }}<el-icon aria-hidden="true"><ArrowUp v-if="genresExpanded" /><ArrowDown v-else /></el-icon></button></div>

    <div class="cine-marquee" aria-hidden="true"><div class="marquee-track"><span v-for="i in 2" :key="i">NOW SHOWING · ACTION · ROMANCE · SCI-FI · COMEDY · THRILLER · ANIMATION · MYSTERY ·&nbsp;</span></div></div>

    <div class="intro-strip"><p><el-icon aria-hidden="true"><Reading /></el-icon><strong>真实片库</strong><span>保留原始 MovieLens 电影标识</span></p><p><el-icon aria-hidden="true"><Search /></el-icon><strong>自由探索</strong><span>按片名与类型发现电影</span></p><RouterLink to="/movies">开始浏览 <span aria-hidden="true">↗</span></RouterLink></div>
    <section class="recommendation-section"><div class="section-heading"><div><p class="eyebrow">MADE FOR YOUR TASTE</p><h2>你的下一部<span class="heading-dot">.</span></h2><p class="muted">评分与收藏记录喜好，推荐功能等待算法接入。</p></div><RouterLink to="/experiments" class="text-link">查看实验室 →</RouterLink></div><div class="recommendation-columns"><AlgorithmPanel label="为你推荐" :endpoint="auth.account ? '/me/recommendations/content' : null" /><AlgorithmPanel label="热门推荐" :endpoint="auth.account ? '/me/recommendations/popular' : null" /></div></section>
    <section class="browse-section"><div class="section-heading"><div><p class="eyebrow">THE FILM ARCHIVE</p><h2>从片库出发<span class="heading-dot">.</span></h2><p class="muted">按原始电影编号展示，探索属于你的下一部。</p></div><RouterLink to="/movies" class="text-link">查看全部 <el-icon aria-hidden="true"><ArrowRight /></el-icon></RouterLink></div><StatePanel :loading="loading" :error="error" :empty="!!data && !data.items.length" @retry="fetchMovies"><div class="movie-grid"><MovieCard v-for="movie in data?.items" :key="movie.movie_id" :movie="movie" /></div></StatePanel></section>
  </div>
</template>

<style scoped>
/* ===== 影院风轮播 ===== */
.hero-carousel { border-radius: 22px; overflow: hidden; box-shadow: 0 28px 64px -24px rgba(6, 34, 12, .5); }
.fc-fallback { height: 440px; }
.fc-slide { position: relative; height: 100%; overflow: hidden; background: linear-gradient(115deg, #0b120e 0%, #10261a 55%, #0a1a12 100%); }
.fc-bg { position: absolute; inset: 0; background-size: cover; background-position: center 22%; filter: blur(34px) brightness(.68) saturate(1.55); transform: scale(1.28); }
.fc-bg::after { content: ''; position: absolute; inset: 0; background: linear-gradient(90deg, rgba(7, 13, 9, .92) 5%, rgba(7, 13, 9, .45) 48%, rgba(7, 13, 9, .25) 80%); }
.fc-inner { position: relative; z-index: 2; height: 100%; display: flex; align-items: center; justify-content: center; gap: clamp(48px, 7vw, 110px); padding: 0 72px; }
.fc-copy { min-width: 0; max-width: 560px; }
.fc-eyebrow { display: flex; align-items: center; gap: 10px; color: #8df5ab; font-size: 11px; letter-spacing: .24em; font-weight: 600; }
.fc-dot { width: 7px; height: 7px; border-radius: 50%; background: #00e676; box-shadow: 0 0 12px #00e676; animation: clPulse 2s ease-in-out infinite; }
@keyframes clPulse { 50% { opacity: .35; } }
.fc-title { color: #fff; font-size: clamp(32px, 3.8vw, 54px); line-height: 1.22; margin: 14px 0 8px; letter-spacing: -.02em; }
.fc-meta { color: #ffd94d; font-size: 13px; letter-spacing: .05em; font-weight: 600; }
.fc-chips { display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap; }
.fc-chip { padding: 4px 13px; font-size: 11px; border-radius: 999px; color: rgba(255, 255, 255, .88); background: rgba(255, 255, 255, .12); border: 1px solid rgba(255, 255, 255, .22); -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px); }
.fc-overview { color: rgba(255, 255, 255, .78); font-size: 14px; line-height: 1.85; margin-top: 14px; max-width: 36em; }
.fc-actions { display: flex; gap: 14px; margin-top: 24px; flex-wrap: wrap; }
.fc-btn-primary { display: inline-flex; align-items: center; gap: 8px; padding: 13px 28px; border-radius: 999px; font-weight: 700; font-size: 14px; color: #03170a; background: linear-gradient(135deg, #3dff8f, #00BE06); box-shadow: 0 10px 26px -8px rgba(0, 230, 118, .55); transition: all .25s ease; }
.fc-btn-primary:hover { transform: translateY(-2px); box-shadow: 0 14px 32px -8px rgba(0, 230, 118, .7); }
.fc-btn-ghost { display: inline-flex; align-items: center; gap: 8px; padding: 12px 24px; border-radius: 999px; font-size: 14px; color: #fff; border: 1px solid rgba(255, 255, 255, .35); background: rgba(255, 255, 255, .08); -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px); transition: all .25s ease; }
.fc-btn-ghost:hover { background: rgba(255, 255, 255, .18); }
.fc-poster { width: 236px; flex-shrink: 0; border-radius: 16px; overflow: hidden; transform: rotate(3.5deg); box-shadow: 0 34px 64px -18px rgba(0, 0, 0, .65), 0 0 0 1px rgba(255, 255, 255, .12); transition: transform .5s cubic-bezier(.2, .8, .3, 1.2); }
.fc-poster:hover { transform: rotate(0deg) scale(1.04); }
.fc-poster :deep(.movie-poster) { border-radius: 16px; aspect-ratio: 2/3; }
/* 装饰元素：超大描边序号 / 竖排侧标 / 计数器 */
.fc-index { position: absolute; top: 14px; right: 44px; z-index: 1; font-size: 96px; font-weight: 800; line-height: 1; letter-spacing: .02em; color: transparent; -webkit-text-stroke: 1.5px rgba(255, 255, 255, .2); pointer-events: none; }
.fc-side { position: absolute; right: 20px; top: 50%; transform: translateY(-50%) rotate(90deg); z-index: 1; font-size: 10px; letter-spacing: .42em; color: rgba(255, 255, 255, .35); pointer-events: none; white-space: nowrap; }
.fc-counter { position: absolute; right: 44px; bottom: 18px; z-index: 1; font-family: "SF Mono", Consolas, monospace; font-size: 13px; letter-spacing: .22em; color: rgba(255, 255, 255, .55); pointer-events: none; }
/* 指示器与箭头 */
.fc-carousel :deep(.el-carousel__button) { width: 20px; height: 4px; border-radius: 2px; background: rgba(255, 255, 255, .35); transition: all .3s ease; }
.fc-carousel :deep(.el-carousel__indicator.is-active .el-carousel__button) { width: 36px; background: #00e676; }
.fc-carousel :deep(.el-carousel__arrow) { background: rgba(0, 0, 0, .4); -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px); width: 44px; height: 44px; }
.fc-carousel :deep(.el-carousel__arrow:hover) { background: rgba(0, 190, 6, .85); }

/* ===== 类型胶囊条：每类专属配色 + 可展开 ===== */
.genre-strip { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 26px; }
.genre-strip-label { display: inline-flex; align-items: center; gap: 8px; font-size: 11px; letter-spacing: .18em; color: var(--muted); font-weight: 600; }
.genre-strip-label::before { content: ''; width: 3px; height: 13px; border-radius: 2px; background: linear-gradient(180deg, #00e676, #00BE06); box-shadow: 0 0 8px rgba(0, 230, 118, .5); }
.genre-chip-link { padding: 8px 20px; border-radius: 999px; font-size: 13px; font-weight: 600; color: var(--gc); background: color-mix(in srgb, var(--gc) 10%, #fff); border: 1px solid color-mix(in srgb, var(--gc) 18%, transparent); transition: all .24s cubic-bezier(.2, .8, .3, 1.2); animation: clGenreIn .35s ease both; }
.genre-chip-link:hover { background: var(--gc); color: #fff; border-color: var(--gc); transform: translateY(-2px) scale(1.04); box-shadow: 0 10px 20px -8px var(--gc); }
@keyframes clGenreIn { from { opacity: 0; transform: translateY(6px); } }
.genre-toggle { display: inline-flex; align-items: center; gap: 5px; padding: 8px 16px; border-radius: 999px; font-size: 12px; font-weight: 600; color: var(--muted); background: #fff; border: 1px dashed #d3d7de; cursor: pointer; transition: all .22s ease; }
.genre-toggle:hover { color: #00BE06; border-color: #00BE06; border-style: solid; background: rgba(0, 190, 6, .05); }

/* ===== 描边大字跑马灯（深色霓虹带） ===== */
.cine-marquee { overflow: hidden; padding: 26px 0; margin-top: 26px; border-radius: 18px; background: linear-gradient(115deg, #0b120e 0%, #10261a 55%, #0a1a12 100%); box-shadow: 0 18px 40px -18px rgba(6, 34, 12, .45); }
.marquee-track { display: flex; width: max-content; animation: clMarquee 32s linear infinite; }
.marquee-track span { font-size: 34px; font-weight: 800; letter-spacing: .12em; white-space: nowrap; color: transparent; -webkit-text-stroke: 1.3px rgba(0, 230, 118, .65); text-shadow: 0 0 24px rgba(0, 230, 118, .18); }
@keyframes clMarquee { to { transform: translateX(-50%); } }

.recommendation-section { margin-top: 30px; }

@media (max-width: 1100px) {
  .fc-inner { padding: 0 44px; gap: 32px; }
  .fc-poster { width: 180px; }
  .fc-index { font-size: 72px; right: 32px; }
  .fc-counter { right: 32px; }
}
@media (max-width: 640px) {
  .fc-inner { padding: 28px 24px; }
  .fc-poster { display: none; }
  .fc-index, .fc-side { display: none; }
  .fc-counter { right: 24px; }
  .fc-title { font-size: 26px; }
  .marquee-track span { font-size: 20px; }
  .fc-fallback { height: 560px; }
}
@media (prefers-reduced-motion: reduce) {
  .marquee-track, .fc-dot { animation: none; }
}
</style>
