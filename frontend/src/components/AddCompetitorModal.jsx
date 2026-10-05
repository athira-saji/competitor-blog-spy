import { useState } from 'react'
import { X } from 'lucide-react'

export default function AddCompetitorModal({ onClose, onAdd }) {
  const [form, setForm] = useState({ name:'', website_url:'', blog_url:'', feed_url:'', sitemap_url:'' })
  const [busy, setBusy] = useState(false)
  const update = e => setForm({ ...form, [e.target.name]: e.target.value })
  const submit = async e => { e.preventDefault(); setBusy(true); try { await onAdd(form); onClose() } finally { setBusy(false) } }
  return <div className="modal-backdrop"><div className="modal"><div className="modal-head"><div><h2>Add competitor</h2><p>The system will automatically investigate RSS, Atom, sitemap and article-page signals.</p></div><button className="icon-button" onClick={onClose}><X size={18}/></button></div>
    <form onSubmit={submit} className="form-grid">
      <label>Competitor name<input name="name" required value={form.name} onChange={update} placeholder="Acme Blog"/></label>
      <label>Website URL<input name="website_url" type="url" required value={form.website_url} onChange={update} placeholder="https://example.com"/></label>
      <label>Blog / article URL <small>optional</small><input name="blog_url" type="url" value={form.blog_url} onChange={update} placeholder="https://example.com/blog"/></label>
      <label>RSS / Atom feed <small>optional</small><input name="feed_url" type="url" value={form.feed_url} onChange={update} placeholder="https://example.com/feed.xml"/></label>
      <label>Sitemap URL <small>optional</small><input name="sitemap_url" type="url" value={form.sitemap_url} onChange={update} placeholder="https://example.com/sitemap.xml"/></label>
      <div className="form-actions"><button type="button" className="button secondary" onClick={onClose}>Cancel</button><button disabled={busy} className="button primary">{busy ? 'Adding…' : 'Add & analyze'}</button></div>
    </form>
  </div></div>
}
