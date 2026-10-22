import { reactive } from 'vue'
import http from '../api'
import type { Movie } from '../types'

const cache = reactive<Record<string, Movie | null>>({})
const pending = new Map<string, Promise<void>>()

export async function ensureMovieTitles(ids: string[]): Promise<void> {
  const missing = ids.filter(id => id && !(id in cache) && !pending.has(id))
  await Promise.all(missing.map(id => {
    const p = (async () => {
      try {
        const { data } = await http.get<Movie>(`/movies/${id}`)
        cache[id] = data
      } catch {
        cache[id] = null
      } finally {
        pending.delete(id)
      }
    })()
    pending.set(id, p)
    return p
  }))
}

export function getMovie(id: string): Movie | null {
  return cache[id] ?? null
}

export function movieTitle(id: string): string {
  const m = cache[id]
  return m ? (m.title_zh || m.movielens_title) : `电影 #${id}`
}
