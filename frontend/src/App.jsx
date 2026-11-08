import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { filterCustomersBySegments } from './analytics.js'
import './App.css'

const TrendChart = lazy(() => import('./TrendChart.jsx'))
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
const PUBLIC_DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'
const apiFetch = (path, options) => fetch(`${API_BASE_URL}${path}`, options)

const emptyForm = {
  complaint_id: '', customer_id: '', complaint_text: '', channel: 'email', severity: 3,
  country: '', state: '', age_group: '', student_status: '', income_bracket: '',
}

function Icon({ name, size = 18 }) {
  const paths = {
    compass: <><circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2.2 4.8-4.8 2.2 2.2-4.8 4.8-2.2Z"/></>,
    overview: <><rect x="3.5" y="3.5" width="7" height="7" rx="1"/><rect x="13.5" y="3.5" width="7" height="4" rx="1"/><rect x="13.5" y="10.5" width="7" height="10" rx="1"/><rect x="3.5" y="13.5" width="7" height="7" rx="1"/></>,
    complaints: <><path d="M7 3.5h7l4 4v13H7a2 2 0 0 1-2-2v-13a2 2 0 0 1 2-2Z"/><path d="M14 3.5v4h4M8.5 12h7M8.5 16h7"/></>,
    customers: <><circle cx="9" cy="8" r="3.5"/><path d="M2.8 20a6.2 6.2 0 0 1 12.4 0M16 5a3.5 3.5 0 0 1 0 6.8M17 14a5 5 0 0 1 4.2 5"/></>,
    upload: <><path d="M12 16V4m-4 4 4-4 4 4"/><path d="M5 14v5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-5"/></>,
    plus: <><path d="M12 5v14M5 12h14"/></>,
    search: <><circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4.2 4.2"/></>,
    arrow: <><path d="M5 12h14m-6-6 6 6-6 6"/></>,
    route: <><circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/><path d="M8 18h3a3 3 0 0 0 3-3v-3a3 3 0 0 1 3-3h1"/></>,
  }
  return <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>
}

function App() {
  const [api, setApi] = useState('checking')
  const [demoMode, setDemoMode] = useState(PUBLIC_DEMO_MODE)
  const [view, setView] = useState('overview')
  const [overview, setOverview] = useState({ complaint_count: 0, affected_customers: 0, high_severity_count: 0, critical_issue_count: 0, channel_count: 0, customer_count: 0 })
  const [complaints, setComplaints] = useState([])
  const [customers, setCustomers] = useState([])
  const [segments, setSegments] = useState([])
  const [trends, setTrends] = useState({ monthly: [], emerging_issues: [] })
  const [segmentFilters, setSegmentFilters] = useState({ country: '', state: '', age_group: '', student_status: '', income_bracket: '' })
  const [issueData, setIssueData] = useState({ latest_analysis: null, items: [], total_issues: 0, unclustered_count: 0, duplicate_submissions: 0 })
  const [selectedIssue, setSelectedIssue] = useState(null)
  const [search, setSearch] = useState('')
  const [channel, setChannel] = useState('')
  const [severity, setSeverity] = useState('')
  const [notice, setNotice] = useState('')
  const [form, setForm] = useState(null)
  const [saving, setSaving] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const fileInput = useRef(null)

  const loadData = useCallback(async () => {
    try {
      const query = new URLSearchParams()
      if (search.trim()) query.set('search', search.trim())
      if (channel) query.set('channel', channel)
      if (severity) query.set('severity', severity)
      const [healthRes, overviewRes, complaintsRes, customersRes, issuesRes, segmentsRes, trendsRes] = await Promise.all([
        apiFetch('/api/health'), apiFetch('/api/analytics/overview'),
        apiFetch(`/api/complaints?${query.toString()}`), apiFetch('/api/customers?limit=200'), apiFetch('/api/issues'),
        apiFetch('/api/analytics/segments'), apiFetch('/api/analytics/trends'),
      ])
      if (![healthRes, overviewRes, complaintsRes, customersRes, issuesRes, segmentsRes, trendsRes].every((response) => response.ok)) throw new Error('Could not load workspace data')
      const [health, overviewData, complaintData, customerData, issueResult, segmentResult, trendResult] = await Promise.all([
        healthRes.json(), overviewRes.json(), complaintsRes.json(), customersRes.json(), issuesRes.json(), segmentsRes.json(), trendsRes.json(),
      ])
      setApi(health.status === 'ok' ? 'online' : 'offline')
      setDemoMode(PUBLIC_DEMO_MODE || health.demo_mode === true)
      setOverview(overviewData)
      setComplaints(complaintData.items)
      setCustomers(customerData.items)
      setIssueData(issueResult)
      setSegments(segmentResult.items)
      setTrends(trendResult)
    } catch {
      setApi('offline')
    }
  }, [search, channel, severity])

  useEffect(() => { loadData() }, [loadData])
  useEffect(() => {
    if (!notice) return undefined
    const timer = window.setTimeout(() => setNotice(''), 5000)
    return () => window.clearTimeout(timer)
  }, [notice])

  const channelCounts = overview.channel_counts || {}
  const filteredSegments = filterCustomersBySegments(segments, segmentFilters)
  const segmentOptions = Object.fromEntries(Object.keys(segmentFilters).map((key) => [key, [...new Set(segments.map((customer) => customer[key]).filter(Boolean))].sort()]))

  const openForm = () => {
    setForm({ ...emptyForm, complaint_id: `CC-${Date.now().toString().slice(-6)}` })
    setView('complaints')
  }

  async function submitComplaint(event) {
    event.preventDefault()
    setSaving(true)
    const payload = {
      complaint_id: form.complaint_id,
      customer_id: form.customer_id || null,
      complaint_text: form.complaint_text,
      channel: form.channel,
      severity: Number(form.severity),
      customer: {
        country: form.country || null, state: form.state || null, age_group: form.age_group || null,
        student_status: form.student_status || null, income_bracket: form.income_bracket || null,
      },
    }
    try {
      const response = await apiFetch('/api/complaints', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Could not save complaint')
      setForm(null)
      setNotice('Complaint saved')
      await loadData()
    } catch (error) {
      setNotice(error.message)
    } finally {
      setSaving(false)
    }
  }

  async function uploadFile(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    const data = new FormData()
    data.append('file', file)
    try {
      const response = await apiFetch('/api/complaints/upload', { method: 'POST', body: data })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Upload failed')
      const firstError = result.errors?.[0]?.error
      setNotice(`${result.added} added · ${result.skipped} skipped${firstError ? ` · ${firstError}` : ''}`)
      await loadData()
    } catch (error) {
      setNotice(error.message)
    }
  }

  async function runAnalysis() {
    setAnalyzing(true)
    try {
      const response = await apiFetch('/api/analysis/run', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ min_cluster_size: 2, duplicate_similarity_threshold: 0.92, duplicate_window_days: 30 }),
      })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Analysis failed')
      setSelectedIssue(null)
      setNotice(`Analysis complete · ${result.issues_found} issue clusters · ${result.duplicate_submissions} repeat submissions linked`)
      await loadData()
    } catch (error) {
      setNotice(error.message)
    } finally {
      setAnalyzing(false)
    }
  }

  async function openIssue(clusterId) {
    try {
      const response = await apiFetch(`/api/issues/${encodeURIComponent(clusterId)}`)
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Could not load issue details')
      setSelectedIssue(result)
    } catch (error) {
      setNotice(error.message)
    }
  }

  const pageTitle = view === 'customers' ? 'Customers' : view === 'complaints' ? 'Complaints' : view === 'issues' ? 'Issues' : view === 'analytics' ? 'Analytics' : view === 'reports' ? 'Reports' : 'Overview'

  return <main className="app-shell min-h-screen flex">
    <aside className="sidebar">
      <a className="brand" href="#overview" onClick={(event) => { event.preventDefault(); setView('overview') }}><span className="brand-mark"><Icon name="compass" size={19} /></span><span>Complaint Compass</span></a>
      <p className="nav-label">Workspace</p>
      <nav aria-label="Main navigation">
        <button className={`nav-item ${view === 'overview' ? 'active' : ''}`} onClick={() => setView('overview')}><Icon name="overview" />Overview</button>
        <button className={`nav-item ${view === 'complaints' ? 'active' : ''}`} onClick={() => setView('complaints')}><Icon name="complaints" />Complaints<span className="nav-count">{overview.complaint_count}</span></button>
        <button className={`nav-item ${view === 'issues' ? 'active' : ''}`} onClick={() => { setView('issues'); setSelectedIssue(null) }}><Icon name="route" />Issues<span className="nav-count">{issueData.items.length}</span></button>
        <button className={`nav-item ${view === 'customers' ? 'active' : ''}`} onClick={() => setView('customers')}><Icon name="customers" />Customers<span className="nav-count">{overview.customer_count}</span></button>
        <button className={`nav-item ${view === 'analytics' ? 'active' : ''}`} onClick={() => setView('analytics')}><Icon name="overview" />Analytics</button>
        <button className={`nav-item ${view === 'reports' ? 'active' : ''}`} onClick={() => setView('reports')}><Icon name="complaints" />Reports</button>
      </nav>
      <div className="sidebar-bottom"><span className="workspace-mark">CC</span><div><strong>Demo workspace</strong><small>{demoMode ? 'Sample data · read-only' : 'Local workspace'}</small></div><span className={`service-dot ${api}`} title={`API ${api}`} /></div>
    </aside>

    <section className="main-panel">
      <header className="topbar"><span>Workspace <b>/</b> {pageTitle}</span><div className={`api-status ${api}`}><i />{api === 'online' ? 'Connected' : api === 'checking' ? 'Connecting' : 'API offline'}</div></header>
      <div className="content">
        <div className="welcome-row"><div><p className="eyebrow">Customer support intake</p><h1>{view === 'overview' ? 'Complaint desk' : pageTitle}</h1><p className="subtitle">{view === 'overview' ? 'Every report in one place, ready to understand.' : view === 'complaints' ? demoMode ? 'Browse the sample reports included in this read-only demo.' : 'Review reports and capture new customer issues.' : view === 'issues' ? 'Explore complaint clusters and their priority scores.' : view === 'analytics' ? 'Track complaint volume and compare customer segments.' : view === 'reports' ? 'Export the latest complaint and issue intelligence.' : 'Customer profiles and the issues they have reported.'}</p>{demoMode && <p className="demo-notice">Public demo · synthetic sample data · read-only</p>}</div>{!demoMode && <div className="header-actions"><button className="button-secondary" onClick={() => fileInput.current?.click()}><Icon name="upload" size={16} />Upload CSV</button><button className="button-primary" onClick={openForm}><Icon name="plus" size={16} />Add complaint</button><input ref={fileInput} className="visually-hidden" type="file" accept=".csv,text/csv" onChange={uploadFile} /></div>}</div>

        {view === 'overview' && <>
          <div className="metric-grid">
            <article className="metric-card"><div className="metric-label">Complaints received</div><strong>{overview.complaint_count.toLocaleString()}</strong><small>All submitted reports</small></article>
            <article className="metric-card"><div className="metric-label">Customers affected</div><strong>{overview.affected_customers.toLocaleString()}</strong><small>Unique customer records</small></article>
            <article className="metric-card"><div className="metric-label">High severity</div><strong>{overview.high_severity_count.toLocaleString()}</strong><small>Severity 4 or 5</small></article>
            <article className="metric-card"><div className="metric-label">Critical issues</div><strong>{overview.critical_issue_count.toLocaleString()}</strong><small>High severity in latest analysis</small></article>
          </div>
          <div className="dashboard-grid">
            <section className="panel recent-panel">
              <div className="panel-heading"><div><h2>Recent complaints</h2><p>New reports from every channel</p></div><button className="text-link" onClick={() => setView('complaints')}>View all <Icon name="arrow" size={15} /></button></div>
              <ComplaintTable items={complaints.slice(0, 5)} emptyText="No reports yet. Add a complaint or upload a CSV to begin." />
            </section>
            <section className="panel sources-panel">
              <div className="panel-heading"><div><h2>Intake channels</h2><p>Reports by source</p></div><span className="route-stamp"><Icon name="route" size={17} /></span></div>
              <div className="channel-list">{['email', 'voice', 'chatbot', 'social', 'web', 'other'].map((name) => <div className="channel-row" key={name}><span className={`channel-pin ${channelCounts[name] ? 'has-data' : ''}`} /><span>{name === 'voice' ? 'Voice calls' : name === 'chatbot' ? 'Chatbot' : name === 'social' ? 'Social media' : name[0].toUpperCase() + name.slice(1)}</span><strong>{channelCounts[name] || 0}</strong></div>)}</div>
              <div className="route-note"><span className="route-line" /><span>Reports stay separate until analysis links them to a common issue</span></div>
            </section>
          </div>
        </>}

        {view === 'analytics' && <>
          <div className="metric-grid analytics-metrics">
            <article className="metric-card"><div className="metric-label">Complaints received</div><strong>{overview.complaint_count.toLocaleString()}</strong><small>All submitted reports</small></article>
            <article className="metric-card"><div className="metric-label">Affected customers</div><strong>{overview.affected_customers.toLocaleString()}</strong><small>Identified customer records</small></article>
            <article className="metric-card"><div className="metric-label">Critical issues</div><strong>{overview.critical_issue_count.toLocaleString()}</strong><small>High severity in latest analysis</small></article>
            <article className="metric-card"><div className="metric-label">Prioritized issues</div><strong>{issueData.total_issues.toLocaleString()}</strong><small>Clusters in latest analysis</small></article>
          </div>
          <div className="dashboard-grid analytics-grid">
            <section className="panel chart-panel"><div className="panel-heading"><div><h2>Complaints over time</h2><p>Monthly submissions across all channels</p></div></div><Suspense fallback={<p className="panel-empty">Loading chart…</p>}><TrendChart data={trends.monthly} /></Suspense></section>
            <section className="panel emerging-panel"><div className="panel-heading"><div><h2>Emerging issues</h2><p>Unique reports in the last 30 days</p></div></div>{trends.emerging_issues.length ? trends.emerging_issues.slice(0, 6).map((item) => <div className="emerging-row" key={item.label}><span><strong>{item.label}</strong><small>{item.recent_reports} recent · {item.previous_reports} prior</small></span><b className={item.change > 0 ? 'trend-up' : ''}>{item.change > 0 ? '+' : ''}{item.change}</b></div>) : <p className="panel-empty">Run analysis and add dated complaints to see emerging issues.</p>}</section>
          </div>
          <section className="panel segment-panel"><div className="panel-heading panel-heading-wrap"><div><h2>Customer intelligence</h2><p>{filteredSegments.length} of {segments.length} customer profiles match</p></div><button className="button-secondary" onClick={() => setSegmentFilters({ country: '', state: '', age_group: '', student_status: '', income_bracket: '' })}>Clear filters</button></div><div className="segment-filters">{[['country','Country'],['state','State / region'],['age_group','Age group'],['student_status','Student status'],['income_bracket','Income bracket']].map(([key,label]) => <label key={key}>{label}<select value={segmentFilters[key]} onChange={(event) => setSegmentFilters({ ...segmentFilters, [key]: event.target.value })}><option value="">All</option>{(segmentOptions[key] || []).map((option) => <option key={option} value={option}>{option}</option>)}</select></label>)}</div><div className="table-scroll"><table><thead><tr><th>Customer</th><th>Country</th><th>State / region</th><th>Age group</th><th>Student</th><th>Income bracket</th><th>Reports</th></tr></thead><tbody>{filteredSegments.slice(0, 100).map((customer) => <tr key={customer.customer_id}><td><strong className="row-id">{customer.customer_id}</strong></td><td>{customer.country || '—'}</td><td>{customer.state || '—'}</td><td>{customer.age_group || '—'}</td><td>{customer.student_status || '—'}</td><td>{customer.income_bracket || '—'}</td><td>{customer.complaint_count}</td></tr>)}</tbody></table></div>{!filteredSegments.length && <p className="panel-empty">No customer profiles match these filters.</p>}</section>
        </>}

        {view === 'reports' && <section className="panel report-panel"><div className="panel-heading"><div><h2>Complaint report</h2><p>Export the current workspace data, including issue labels and priority scores.</p></div></div><div className="report-actions"><a className="button-primary" href="/api/analytics/report.csv" download><Icon name="upload" size={16} />Download CSV</a><button className="button-secondary" onClick={() => window.print()}>Print / Save as PDF</button></div><div className="report-preview"><div><span>Complaints</span><strong>{overview.complaint_count.toLocaleString()}</strong></div><div><span>Customer profiles</span><strong>{overview.customer_count.toLocaleString()}</strong></div><div><span>Prioritized issues</span><strong>{issueData.total_issues.toLocaleString()}</strong></div><div><span>Repeat submissions</span><strong>{issueData.duplicate_submissions.toLocaleString()}</strong></div></div><div className="panel-heading"><div><h2>Highest priority issues</h2><p>Included in the on-screen PDF print preview</p></div></div><div className="table-scroll"><table><thead><tr><th>Issue</th><th>Priority</th><th>Customers</th><th>Unique reports</th></tr></thead><tbody>{issueData.items.slice(0, 10).map((issue) => <tr key={issue.cluster_id}><td>{issue.label}</td><td>{Number(issue.priority_score).toFixed(1)}</td><td>{issue.affected_customers}</td><td>{issue.complaint_count}</td></tr>)}</tbody></table></div></section>}

        {view === 'complaints' && <section className="panel data-panel">
          <div className="panel-heading panel-heading-wrap"><div><h2>All complaints</h2><p>{complaints.length} shown · {overview.complaint_count} total reports</p></div><div className="table-filters"><label className="search-box"><Icon name="search" size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search complaints" /></label><select value={channel} onChange={(event) => setChannel(event.target.value)} aria-label="Filter by channel"><option value="">All channels</option><option value="email">Email</option><option value="voice">Voice calls</option><option value="chatbot">Chatbot</option><option value="social">Social media</option><option value="web">Web</option><option value="other">Other</option></select><select value={severity} onChange={(event) => setSeverity(event.target.value)} aria-label="Filter by severity"><option value="">All severity</option><option value="5">Critical</option><option value="4">High</option><option value="3">Medium</option><option value="2">Low</option><option value="1">Minor</option></select></div></div>
          <ComplaintTable items={complaints} emptyText="No complaints match these filters." />
        </section>}

        {view === 'issues' && <section className="panel data-panel issues-view">
          <div className="panel-heading panel-heading-wrap"><div><h2>{selectedIssue ? selectedIssue.issue.label : 'Top 10 prioritized issues'}</h2><p>{selectedIssue ? selectedIssue.issue.representative_text : 'Ranked by severity, unique report frequency, and affected customers.'}</p></div><div className="issue-actions">{selectedIssue && <button className="button-secondary" onClick={() => setSelectedIssue(null)}>All issues</button>}{!demoMode && <button className="button-primary" onClick={runAnalysis} disabled={analyzing || overview.complaint_count === 0}><Icon name="route" size={16} />{analyzing ? 'Analyzing…' : 'Analyze complaints'}</button>}</div></div>
          <details className="score-method"><summary>How priority is calculated</summary><p><strong>Priority = 0.4S + 0.3F + 0.3I</strong>, rounded to two decimals. S maps average severity from 1–5 to 0–100. F maps unique reports and I maps affected customers relative to the largest value in this analysis run. Repeat submissions are excluded from unique report frequency.</p></details>
          {selectedIssue ? <>
            <div className="issue-summary"><span><strong>{Number(selectedIssue.issue.priority_score).toFixed(1)}</strong> priority score</span><span><strong>{selectedIssue.issue.affected_customers}</strong> affected customers</span><span><strong>{selectedIssue.issue.complaint_count}</strong> unique reports</span><span><strong>{selectedIssue.issue.duplicate_count}</strong> repeat submissions linked</span></div>
            <div className="score-components"><div><span>Severity · 40%</span><strong>{Number(selectedIssue.issue.severity_score).toFixed(1)}</strong></div><div><span>Frequency · 30%</span><strong>{Number(selectedIssue.issue.frequency_score).toFixed(1)}</strong></div><div><span>Customer impact · 30%</span><strong>{Number(selectedIssue.issue.impact_score).toFixed(1)}</strong></div><div><span>Average severity</span><strong>{selectedIssue.issue.average_severity} / 5</strong></div></div>
            <div className="issue-evidence"><h3>Reports in this issue</h3>{selectedIssue.complaints.map((item) => <article className="evidence-row" key={item.complaint_id}><span className="route-mark"><Icon name="route" size={14} /></span><div><strong>{item.complaint_text}</strong><small>{item.complaint_id} · {item.customer_id || 'Customer unknown'} · {item.channel}</small></div>{item.duplicate_of && <span className="duplicate-tag">Repeat of {item.duplicate_of}</span>}</article>)}</div>
          </> : issueData.items.length ? <>
            {issueData.latest_analysis && <div className="analysis-note">Last run {new Date(issueData.latest_analysis.created_at).toLocaleString()} · {issueData.latest_analysis.embedding_model} · {issueData.latest_analysis.clustering_method}{issueData.latest_analysis.label_model ? ` · labels via ${issueData.latest_analysis.label_model}` : ' · labels via local keywords'}</div>}
            <div className="issue-summary"><span><strong>{issueData.total_issues}</strong> issues found</span><span><strong>{issueData.duplicate_submissions}</strong> repeat submissions linked</span><span><strong>{issueData.unclustered_count}</strong> unclustered reports</span></div>
            <div className="issue-list">{issueData.items.map((issue) => <button className="issue-row" key={issue.cluster_id} onClick={() => openIssue(issue.cluster_id)}><span className="issue-route"><Icon name="route" size={17} /></span><span className="issue-name"><strong>{issue.label}</strong><small>{issue.representative_text}</small></span><span className="issue-stat priority-stat"><strong>{Number(issue.priority_score).toFixed(1)}</strong><small>priority</small></span><span className="issue-stat"><strong>{issue.affected_customers}</strong><small>customers</small></span><span className="issue-stat"><strong>{issue.complaint_count}</strong><small>unique</small></span><span className="issue-stat"><strong>{issue.duplicate_count}</strong><small>repeats</small></span><Icon name="arrow" size={16} /></button>)}</div>
          </> : <EmptyState title={overview.complaint_count ? 'Run analysis to find recurring issues' : 'Add complaints before analyzing'} text={overview.complaint_count ? 'The local embedding model will compare complaint meaning, cluster related reports, and link likely repeat submissions from the same customer.' : 'Upload the sample dataset or add customer reports, then run analysis to discover issue groups.'} />}
        </section>}

        {view === 'customers' && <section className="panel data-panel">
          <div className="panel-heading"><div><h2>Customer records</h2><p>{customers.length} profiles · details are collected from complaint submissions</p></div></div>
          {customers.length ? <div className="table-scroll"><table><thead><tr><th>Customer</th><th>Country / state</th><th>Age group</th><th>Student</th><th>Income bracket</th><th>Reports</th></tr></thead><tbody>{customers.map((customer) => <tr key={customer.customer_id}><td><strong className="row-id">{customer.customer_id}</strong></td><td>{[customer.country, customer.state].filter(Boolean).join(' · ') || '—'}</td><td>{customer.age_group || '—'}</td><td>{customer.student_status || '—'}</td><td>{customer.income_bracket || '—'}</td><td>{customer.complaint_count}</td></tr>)}</tbody></table></div> : <EmptyState title="No customer profiles yet" text="Add a customer ID when submitting a complaint, or include one in your CSV. Profile fields are optional." />}
        </section>}

        {form && <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setForm(null) }}><section className="form-dialog" role="dialog" aria-modal="true" aria-labelledby="form-title"><div className="dialog-heading"><div><p className="eyebrow">New report</p><h2 id="form-title">Add complaint</h2></div><button className="close-button" aria-label="Close" onClick={() => setForm(null)}>×</button></div><form onSubmit={submitComplaint}><div className="form-grid"><label>Complaint ID<input required maxLength="100" value={form.complaint_id} onChange={(e) => setForm({ ...form, complaint_id: e.target.value })} /></label><label>Customer ID <span className="optional">Optional</span><input maxLength="100" value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })} placeholder="CUS-1042" /></label><label className="full-field">What happened?<textarea required minLength="3" maxLength="10000" rows="4" value={form.complaint_text} onChange={(e) => setForm({ ...form, complaint_text: e.target.value })} placeholder="Describe the customer's issue" /></label><label>Source<select value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}><option value="email">Email</option><option value="voice">Voice call</option><option value="chatbot">Chatbot</option><option value="social">Social media</option><option value="web">Web</option><option value="other">Other</option></select></label><label>Severity<select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}><option value="1">1 · Minor</option><option value="2">2 · Low</option><option value="3">3 · Medium</option><option value="4">4 · High</option><option value="5">5 · Critical</option></select></label><div className="full-field profile-divider">Customer profile <span>Optional details help compare issue impact by group</span></div><label>Country<input value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value })} /></label><label>State / region<input value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} /></label><label>Age group<input value={form.age_group} onChange={(e) => setForm({ ...form, age_group: e.target.value })} placeholder="18–24" /></label><label>Student status<select value={form.student_status} onChange={(e) => setForm({ ...form, student_status: e.target.value })}><option value="">Not provided</option><option value="yes">Student</option><option value="no">Not a student</option></select></label><label className="full-field">Income bracket<input value={form.income_bracket} onChange={(e) => setForm({ ...form, income_bracket: e.target.value })} placeholder="Optional" /></label></div><div className="dialog-actions"><button type="button" className="button-secondary" onClick={() => setForm(null)}>Cancel</button><button className="button-primary" disabled={saving}>{saving ? 'Saving…' : 'Save complaint'}</button></div></form></section></div>}

        {notice && <div className="toast" role="status">{notice}<button onClick={() => setNotice('')} aria-label="Dismiss">×</button></div>}
        <footer>Complaint Compass <span>·</span> Intake and customer records</footer>
      </div>
    </section>
  </main>
}

function ComplaintTable({ items, emptyText }) {
  if (!items.length) return <EmptyState title="No complaints yet" text={emptyText} />
  return <div className="table-scroll"><table><thead><tr><th>Complaint</th><th>Customer</th><th>Source</th><th>Severity</th><th>Issue link</th><th>Received</th></tr></thead><tbody>{items.map((item) => <tr key={item.complaint_id}><td className="complaint-cell"><span className="route-mark"><Icon name="route" size={14} /></span><div><strong>{item.complaint_text}</strong><small>{item.complaint_id}</small></div></td><td>{item.customer_id || '—'}</td><td><span className="source-label"><span className="source-dot" />{item.channel}</span></td><td><span className={`severity severity-${item.severity}`}>{['', 'Minor', 'Low', 'Medium', 'High', 'Critical'][item.severity]}</span></td><td className="issue-link-cell">{item.duplicate_of ? <span className="duplicate-tag">Repeat of {item.duplicate_of}</span> : item.issue_label || '—'}</td><td>{new Date(item.submitted_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</td></tr>)}</tbody></table></div>
}

function EmptyState({ title, text }) {
  return <div className="empty-state"><span className="empty-route"><Icon name="route" size={21} /></span><h3>{title}</h3><p>{text}</p></div>
}

export default App
