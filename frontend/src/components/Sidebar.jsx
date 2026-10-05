import { Activity, LayoutDashboard, Radar, Server, ShieldCheck, Globe2 } from 'lucide-react'

export default function Sidebar({ page, setPage, monitoring }) {
  const items = [
    ['dashboard', 'Dashboard', LayoutDashboard],
    ['competitors', 'Competitors', Globe2],
    ['monitoring', 'Monitoring', Radar],
    ['checks', 'Checks', Server],
  ]

  return <aside className="sidebar">
    <div className="brand">
      <div className="brand-icon"><ShieldCheck size={20}/></div>
      <div>
        <strong>Blog Spy</strong>
        <span>Content Intelligence</span>
      </div>
    </div>

    <nav>
      {items.map(([id, label, Icon]) =>
        <button
          key={id}
          className={page === id ? 'nav-item active' : 'nav-item'}
          onClick={() => setPage(id)}
        >
          <Icon size={18}/>
          <span>{label}</span>
        </button>
      )}
    </nav>

    <div className="sidebar-bottom">
      <Activity size={16}/>
      <span>{monitoring ? 'Monitoring active' : 'Monitoring paused'}</span>
      <i className={monitoring ? 'dot on' : 'dot'} />
    </div>
  </aside>
}