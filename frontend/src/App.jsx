import { useEffect, useState } from 'react'
import { Bell, Search, X } from 'lucide-react'
import Sidebar from './components/Sidebar'
import AddCompetitorModal from './components/AddCompetitorModal'
import Dashboard from './pages/Dashboard'
import Competitors from './pages/Competitors'
import Articles from './pages/Articles'
import Monitoring from './pages/Monitoring'
import Checks from './pages/Checks'
import { api } from './services/api'

function ArticleDrawer({ article, onClose }) {
  if (!article) return null
  return <div className="drawer-backdrop" onClick={onClose}><aside className="drawer" onClick={e => e.stopPropagation()}><div className="drawer-head"><div><p className="eyebrow">Detected article</p><h2>{article.title}</h2></div><button className="icon-button" onClick={onClose}><X size={18}/></button></div><div className="detail-grid"><div><span>Source</span><b>{article.competitor_name}</b></div><div><span>Method</span><b>{article.detection_method}</b></div><div><span>Published</span><b>{article.published_at ? new Date(article.published_at).toLocaleString() : 'Not available'}</b></div><div><span>Detected</span><b>{new Date(article.discovered_at).toLocaleString()}</b></div><div><span>Delay</span><b>{article.detection_delay_seconds == null ? 'Unknown' : `${Math.round(article.detection_delay_seconds)} seconds`}</b></div><div><span>Author</span><b>{article.author || 'Unknown'}</b></div></div>{article.featured_image && <img className="article-image" src={article.featured_image} alt=""/>}<p className="article-body">{article.body || 'No article body was extracted.'}</p><a className="button primary full" href={article.source_url} target="_blank" rel="noreferrer">Open original article</a></aside></div>
}

export default function App() {
  const [page, setPage] = useState('dashboard')
  const [stats, setStats] = useState({})
  const [competitors, setCompetitors] = useState([])
  const [articles, setArticles] = useState([])
  const [checks, setChecks] = useState([])
  const [health, setHealth] = useState(null)
  const [modal, setModal] = useState(false)
  const [article, setArticle] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    try {
      const [s, c, a, ch, h] = await Promise.all([api.stats(), api.competitors(), api.articles(), api.checks(), api.health()])
      setStats(s); setCompetitors(c); setArticles(a); setChecks(ch); setHealth(h); setError('')
    } catch (e) { setError(e.message) }
  }
  useEffect(() => { load(); const timer = setInterval(load, 15000); return () => clearInterval(timer) }, [])

  const add = async data => { await api.addCompetitor(data); await load() }
  const toggle = async c => { await api.toggle(c.id, !c.enabled); await load() }
  const analyze = async id => { await api.analyze(id); await load() }
  const remove = async id => { if (confirm('Delete this competitor and its detected articles?')) { await api.deleteCompetitor(id); await load() } }
  const run = async () => { setRunning(true); try { await api.runMonitoring(); setTimeout(load, 1500) } finally { setTimeout(() => setRunning(false), 1200) } }

  return <div className="app-shell"><Sidebar page={page} setPage={setPage} monitoring={health?.status === 'ok'}/><main className="main"><header className="topbar"><div className="search"><Search size={17}/><span>Competitor content monitoring</span></div><div className="top-actions"><span className="live-pill"><i/> Live monitoring</span><button className="icon-button"><Bell size={18}/></button></div></header>{error && <div className="error-banner">Backend unavailable: {error}. Start FastAPI on port 8000.</div>}
    {page === 'dashboard' && <Dashboard stats={stats} articles={articles} onOpenArticle={setArticle}/>} 
    {page === 'competitors' && <Competitors competitors={competitors} onAdd={() => setModal(true)} onToggle={toggle} onAnalyze={analyze} onDelete={remove}/>} 
    {page === 'articles' && <Articles articles={articles} onOpenArticle={setArticle}/>} 
    {page === 'monitoring' && <Monitoring health={health} running={running} onRun={run}/>} 
    {page === 'checks' && <Checks checks={checks}/>} 
  </main>{modal && <AddCompetitorModal onClose={() => setModal(false)} onAdd={add}/>}<ArticleDrawer article={article} onClose={() => setArticle(null)}/></div>
}
