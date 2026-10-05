const API = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    try { const data = await res.json(); message = data.detail || message } catch {}
    throw new Error(message)
  }
  return res.status === 204 ? null : res.json()
}

export const api = {
  health: () => request('/api/health'),
  stats: () => request('/api/dashboard/stats'),
  competitors: () => request('/api/competitors'),
  addCompetitor: (data) =>
  request('/api/competitors', {
    method: 'POST',
    body: JSON.stringify({
      name: data.name,
      website_url: data.website_url,
      blog_url: data.blog_url || null,
      feed_url: data.feed_url || null,
      sitemap_url: data.sitemap_url || null,
    }),
  }),
  analyze: (id) => request(`/api/competitors/${id}/analyze`, { method: 'POST' }),
  toggle: (id, enabled) => request(`/api/competitors/${id}/toggle`, { method: 'PATCH', body: JSON.stringify({ enabled }) }),
  deleteCompetitor: (id) => request(`/api/competitors/${id}`, { method: 'DELETE' }),
  runMonitoring: () => request('/api/monitoring/run', { method: 'POST' }),
  articles: () => request('/api/articles?limit=200'),
  article: (id) => request(`/api/articles/${id}`),
  checks: () => request('/api/checks?limit=200'),
}
