import { RefreshCw, Pause, Play, Trash2 } from 'lucide-react'
import { formatDate } from '../lib/format'

export default function CompetitorTable({ competitors, onToggle, onAnalyze, onDelete }) {
  if (!competitors.length) return <div className="empty"><h3>No competitors yet</h3><p>Add a website and Blog Spy will investigate its available monitoring sources.</p></div>
  return <div className="table-wrap"><table><thead><tr><th>Competitor</th><th>Status</th><th>Strategy</th><th>Last checked</th><th>Last detection</th><th>Actions</th></tr></thead><tbody>{competitors.map(c => <tr key={c.id}><td><div className="site"><strong>{c.name}</strong><a href={c.website_url} target="_blank" rel="noreferrer">{c.website_url}</a></div></td><td><span className={`badge ${c.status}`}>{c.status}</span></td><td><span className="strategy">{c.strategy || 'Investigating…'}</span></td><td>{formatDate(c.last_checked_at)}</td><td>{formatDate(c.last_successful_detection)}</td><td><div className="actions"><button title="Analyze" onClick={() => onAnalyze(c.id)}><RefreshCw size={15}/></button><button title={c.enabled ? 'Pause' : 'Enable'} onClick={() => onToggle(c)}>{c.enabled ? <Pause size={15}/> : <Play size={15}/>}</button><button title="Delete" onClick={() => onDelete(c.id)}><Trash2 size={15}/></button></div></td></tr>)}</tbody></table></div>
}
