export function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

export function formatDelay(seconds) {
  if (seconds === null || seconds === undefined) return 'Unknown'
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const sec = s % 60
  if (m < 60) return `${m}m ${sec}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m ${sec}s`
}
