import { ExternalLink } from 'lucide-react'
import { formatDate, formatDelay } from '../lib/format'

export default function ArticleTable({ articles, onOpen }) {
  if (!articles.length) return <div className="empty"><h3>No articles detected</h3><p>Run a monitoring cycle or wait for the background worker to discover new content.</p></div>
  return <div className="table-wrap"><table><thead><tr><th>Article</th><th>Source</th><th>Published</th><th>Detected</th><th>Delay</th><th>Method</th></tr></thead><tbody>{articles.map(a => <tr key={a.id} className="click-row" onClick={() => onOpen?.(a)}><td><div className="article-title"><strong>{a.title || 'Untitled article'}</strong><span>{a.author || 'Unknown author'}</span></div></td><td>{a.competitor_name || '—'}</td><td>{formatDate(a.published_at)}</td><td>{formatDate(a.discovered_at)}</td><td><span className={`delay ${a.detection_delay_seconds > 300 ? 'slow' : ''}`}>{formatDelay(a.detection_delay_seconds)}</span></td><td><span className="method">{a.detection_method}</span></td></tr>)}</tbody></table></div>
}
