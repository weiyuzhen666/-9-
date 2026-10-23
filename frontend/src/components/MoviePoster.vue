<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Film } from '@element-plus/icons-vue'

const props = withDefaults(
  defineProps<{
    path?: string | null
    title: string
    genres?: string[] | null
    year?: string | number | null
    tmdbId?: string | number | null
  }>(),
  { genres: null, year: null, tmdbId: null },
)

const failed = ref(false)
watch(() => [props.path, props.tmdbId], () => { failed.value = false })

// 优先级 1: 本地真实海报（下载到 models/business/posters/ 下）
// 通过后端 /api/v1/posters/movie_{tmdb_id}.jpg 接口 serve
const localPosterSrc = computed(() => {
  if (!props.tmdbId) return null
  return `/api/v1/posters/movie_${props.tmdbId}.jpg`
})

// 优先级 2: 真实 poster_path 拼 TMDb CDN
const remotePosterSrc = computed(() => {
  if (!props.path) return null
  if (/^https?:\/\//i.test(props.path)) return props.path
  if (/^\/[a-zA-Z0-9._-]+\.(jpg|jpeg|png|webp)$/i.test(props.path)) {
    return `https://image.tmdb.org/t/p/w342${props.path}`
  }
  return null
})

// —— SVG 占位海报（最后兜底） ——

const GENRE_PALETTES: Record<string, [string, string, string]> = {
  Action: ['#6B1F0F', '#D94F2A', '#FFB347'],
  Adventure: ['#0D4F2E', '#2E8B57', '#8FD9A8'],
  Animation: ['#3B2E6E', '#6A5ACD', '#B8A5E8'],
  Children: ['#8A3A00', '#F08A3E', '#FFD89B'],
  Comedy: ['#8A4B00', '#E8A030', '#FFD97A'],
  Crime: ['#0F1B3D', '#2B4A8C', '#7BA4E8'],
  Documentary: ['#4A3A1F', '#9A7A3F', '#E0C78A'],
  Drama: ['#1B1F4A', '#3D4280', '#9AA0D8'],
  Fantasy: ['#3E1A5F', '#7A3AA8', '#D89BE8'],
  Horror: ['#2A0F1A', '#6B1F3D', '#D87BA0'],
  Romance: ['#6E1F3E', '#C74A7A', '#FFB4CC'],
  'Sci-Fi': ['#0A2647', '#1E5AA8', '#5EC4FF'],
  Thriller: ['#3A0F0F', '#8A2A2A', '#E87A7A'],
  War: ['#3A331F', '#6E623E', '#B8AA6E'],
  Western: ['#6E441F', '#C78A3F', '#FFD08A'],
  'Film-Noir': ['#1F1F2A', '#3A3A4A', '#808099'],
  Musical: ['#8A1F6E', '#D93FA8', '#FF99D8'],
  Mystery: ['#1F1F4A', '#3F3F8A', '#8A8AD8'],
  IMAX: ['#1A2A3A', '#2E5A8C', '#7AB4E8'],
}
const DEFAULT_PALETTE: [string, string, string] = ['#1A2A3A', '#2E5A8C', '#7AB4E8']

function pickPalette(genres: string[] | null | undefined): [string, string, string] {
  if (!genres?.length) return DEFAULT_PALETTE
  for (const g of genres) if (GENRE_PALETTES[g]) return GENRE_PALETTES[g]
  return DEFAULT_PALETTE
}

const GENRE_CN: Record<string, string> = {
  Action: '动作', Adventure: '冒险', Animation: '动画', Children: '儿童',
  Comedy: '喜剧', Crime: '犯罪', Documentary: '纪录', Drama: '剧情',
  Fantasy: '奇幻', 'Film-Noir': '黑色电影', Horror: '恐怖', Musical: '歌舞',
  Mystery: '悬疑', Romance: '爱情', 'Sci-Fi': '科幻', Thriller: '惊悚',
  War: '战争', Western: '西部', IMAX: 'IMAX',
}

function wrapTitle(text: string, max = 8): string[] {
  const cleaned = text.replace(/\s*\([^)]*\)\s*$/, '').trim()
  if (cleaned.length <= max) return [cleaned]
  const lines: string[] = []
  let buf = ''
  for (const ch of cleaned) {
    buf += ch
    if (buf.length >= max) { lines.push(buf); buf = '' }
  }
  if (buf) lines.push(buf)
  return lines.slice(0, 3)
}

const fallbackSvg = computed(() => {
  const [dark, mid, light] = pickPalette(props.genres)
  const cnTag = props.genres?.[0] ? (GENRE_CN[props.genres[0]] || props.genres[0]) : '电影'
  const lines = wrapTitle(props.title || 'Untitled')
  const yearStr = props.year ? ` · ${props.year}` : ''
  const titleHeight = lines.length <= 2 ? 19 : 16
  const titleY = lines.length === 1 ? 76 : lines.length === 2 ? 70 : 65

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 140 210" preserveAspectRatio="xMidYMid slice">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${dark}"/>
      <stop offset="60%" stop-color="${mid}"/>
      <stop offset="100%" stop-color="${dark}"/>
    </linearGradient>
    <radialGradient id="halo" cx="0.5" cy="0.3" r="0.7">
      <stop offset="0%" stop-color="${light}" stop-opacity="0.55"/>
      <stop offset="60%" stop-color="${mid}" stop-opacity="0.2"/>
      <stop offset="100%" stop-color="${dark}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="stripe" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="${light}" stop-opacity="0"/>
      <stop offset="50%" stop-color="${light}" stop-opacity="0.7"/>
      <stop offset="100%" stop-color="${light}" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect width="140" height="210" fill="url(#bg)"/>
  <rect width="140" height="210" fill="url(#halo)"/>
  <polygon points="0,180 140,160 140,210 0,210" fill="${dark}" opacity="0.55"/>
  <rect x="0" y="150" width="140" height="2" fill="url(#stripe)"/>
  <g font-family="-apple-system,Helvetica,Arial,sans-serif" font-weight="700" fill="#fff">
${lines.map((ln, i) => `    <text x="70" y="${titleY + i * (titleHeight + 4)}" text-anchor="middle" font-size="${titleHeight}" dominant-baseline="middle" paint-order="stroke" stroke="${dark}" stroke-width="2.5">${ln}</text>\n`).join('')}
  </g>
  <text x="70" y="172" text-anchor="middle" font-family="-apple-system,Helvetica,Arial,sans-serif" font-size="13" font-weight="500" fill="${light}" opacity="0.9">${cnTag}${yearStr}</text>
  <text x="70" y="195" text-anchor="middle" font-family="Consolas,monospace" font-size="8" fill="${light}" opacity="0.45">CINELAB · POSTER</text>
</svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
})

// 尝试顺序: local → remote → svg
const sources = computed(() => {
  const list: (string | null)[] = []
  if (localPosterSrc.value) list.push(localPosterSrc.value)
  if (remotePosterSrc.value) list.push(remotePosterSrc.value)
  list.push(fallbackSvg.value)  // 永远有 fallback
  return list.filter(Boolean) as string[]
})

// 当前生效的 src
const effectiveSrc = ref<string>('')

// 尝试下一个可用源（当 img onerror 时）
const sourceIdx = ref(0)
function tryNextSource() {
  sourceIdx.value++
  if (sourceIdx.value >= sources.value.length) return
  effectiveSrc.value = sources.value[sourceIdx.value]
  // 如果是 SVG fallback，不再重试
  if (effectiveSrc.value.startsWith('data:image/svg+xml')) return
}

watch(sources, (s) => {
  sourceIdx.value = 0
  effectiveSrc.value = s[0] || ''
}, { immediate: true })

const isPlaceholder = computed(() => effectiveSrc.value.startsWith('data:image/svg+xml'))
</script>

<template>
  <div class="movie-poster" :class="{ placeholder: isPlaceholder }">
    <img
      v-if="effectiveSrc"
      :src="effectiveSrc"
      :alt="title + '海报'"
      loading="lazy"
      @error="tryNextSource"
      referrerpolicy="no-referrer"
    />
    <div v-else class="poster-fallback placeholder" role="img" :aria-label="title">
      <el-icon><Film /></el-icon>
      <span>暂无海报</span>
    </div>
  </div>
</template>

<style scoped>
.movie-poster {
  width: 100%;
  aspect-ratio: 2/3;
  position: relative;
  background: #eef1f5;
  border-radius: 6px;
  overflow: hidden;
}
.movie-poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.movie-poster.placeholder {
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.12);
}
.poster-fallback {
  width: 100%; height: 100%;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; color: #888; font-size: 12px;
}
</style>
