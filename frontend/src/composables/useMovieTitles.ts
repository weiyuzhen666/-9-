import { reactive } from 'vue'
import http from '../api'
import type { Movie } from '../types'

const cache = reactive<Record<string, string>>({})
const pending = new Map<string, Promise<void>>()

export async function ensureMovieTitles(ids: string[]): Promise<void> {
  const missing = ids.filter(id => id && !(id in cache) && !pending.has(id))
  await Promise.all(missing.map(id => {
    const p = (async () => {
      try {
        const { data } = await http.get<Movie>(`/movies/${id}`)
        cache[id] = data.title_zh || data.movielens_title
      } catch {
        cache[id] = ''
      } finally {
        pending.delete(id)
      }
    })()
    pending.set(id, p)
    return p
  }))
}

export function movieTitle(id: string): string {
  return cache[id] || `电影 #${id}`
}
