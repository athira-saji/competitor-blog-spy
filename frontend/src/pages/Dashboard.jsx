import StatCard from '../components/StatCard'
import ArticleTable from '../components/ArticleTable'
import { formatDelay } from '../lib/format'

export default function Dashboard({ stats, articles, onOpenArticle }) {
  return <div className="page"><div className="page-title"><div><p className="eyebrow">Overview</p><h1>Monitoring dashboard</h1><p>Track competitor publications and prove detection performance.</p></div></div>
    <div className="stats">
      <StatCard
        label="Websites"
        value={stats.competitors ?? 0}
        sub={`${stats.enabled_competitors ?? 0} currently enabled`}
      />
      <StatCard
        label="Articles detected"
        value={stats.articles ?? 0}
        sub="New detections"
      />
      <StatCard
        label="Average detection"
        value={formatDelay(stats.average_detection_seconds)}
        sub="Across new detections"
        tone="blue"
      />
      <StatCard
        label="Failed checks"
        value={stats.failed_checks ?? 0}
        sub="Checks requiring attention"
        tone="warning"
      />
    </div>

    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Detection performance</h2>
          <p>Exact delays are retained even when they exceed the five-minute target.</p>
        </div>
        <div className="performance">
          <span>Fastest <b>{formatDelay(stats.fastest_detection_seconds)}</b></span>
          <span>Slowest <b>{formatDelay(stats.slowest_detection_seconds)}</b></span>
        </div>
      </div>
    </section>

    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Latest detected articles</h2>
          <p>Newest content discovered by the monitoring worker.</p>
        </div>
      </div>

      <ArticleTable
        articles={stats.recent_articles ?? []}
        onOpen={onOpenArticle}
      />
    </section>
  </div>
}