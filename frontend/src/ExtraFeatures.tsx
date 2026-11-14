import { useEffect, useState, type FormEvent } from 'react'
import { createFloodReport, deleteFloodReport, getFamilyPlan, getFloodReports, saveFamilyPlan, type FamilyPlanPayload, type FloodReport, type AddressLookupResult } from './api'
import { subscribeAuth } from './auth'

const defaultPlan: FamilyPlanPayload = {
  meeting_place: '', emergency_contact: '', notes: '',
  water_ready: false, medication_ready: false, documents_ready: false, evacuation_route_ready: false,
}

function FeatureShell({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return (
    <main className="w-full px-5 py-7 sm:px-8 lg:py-10">
      <div className="mx-auto max-w-4xl">
        <p className="mb-2 text-sm font-semibold uppercase tracking-[0.18em] text-tide-400">{eyebrow}</p>
        <h1 className="text-3xl font-bold text-white sm:text-4xl">{title}</h1>
        {children}
      </div>
    </main>
  )
}

const checklist: Array<[keyof FamilyPlanPayload, string]> = [
  ['water_ready', 'Store drinking water and shelf-stable food'],
  ['medication_ready', 'Pack essential medication and first-aid supplies'],
  ['documents_ready', 'Protect copies of IDs and insurance documents'],
  ['evacuation_route_ready', 'Identify a safe evacuation route and official shelter guidance'],
]

export function FamilyFloodPlanView() {
  const [plan, setPlan] = useState<FamilyPlanPayload>(defaultPlan)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState('')
  const [version, setVersion] = useState(0)

  useEffect(() => subscribeAuth(() => { setPlan(defaultPlan); setVersion(v => v + 1) }), [])
  useEffect(() => {
    let active = true
    setLoading(true)
    getFamilyPlan()
      .then(value => { if (active) { setPlan(value); setStatus('') } })
      .catch(err => { if (active) setStatus(err instanceof Error ? err.message : 'Unable to load the plan') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [version])

  function change<K extends keyof FamilyPlanPayload>(field: K, value: FamilyPlanPayload[K]) {
    setPlan(current => ({ ...current, [field]: value }))
    setStatus('')
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setStatus('')
    try {
      setPlan(await saveFamilyPlan(plan))
      setStatus('Your family plan was saved securely.')
    } catch (err) { setStatus(err instanceof Error ? err.message : 'Unable to save your plan') }
    finally { setSaving(false) }
  }

  return <FeatureShell eyebrow="Personal preparedness" title="Family Flood Plan">
    <p className="mt-3 text-slate-300">Create a practical household plan. Only you can view and update your saved information.</p>
    <form onSubmit={e => { void save(e) }} className="mt-6 space-y-5 rounded-3xl border border-slate-700 bg-ink-900 p-6">
      <label className="block text-sm font-medium text-slate-200">Family meeting location
        <input maxLength={240} value={plan.meeting_place} onChange={e => change('meeting_place', e.target.value)} className="mt-2 w-full rounded-lg border border-slate-600 bg-ink-950 p-3 text-white" placeholder="A meeting place outside the flood-prone area" />
      </label>
      <label className="block text-sm font-medium text-slate-200">Emergency contact (name and number)
        <input maxLength={200} value={plan.emergency_contact} onChange={e => change('emergency_contact', e.target.value)} className="mt-2 w-full rounded-lg border border-slate-600 bg-ink-950 p-3 text-white" />
      </label>
      <fieldset className="space-y-3">
        <legend className="mb-2 font-semibold text-white">Preparation checklist</legend>
        {checklist.map(([field, label]) => <label key={field} className="flex items-start gap-3 text-slate-200">
          <input type="checkbox" checked={Boolean(plan[field])} onChange={e => change(field, e.target.checked)} className="mt-1 accent-sky-400" />
          {label}
        </label>)}
      </fieldset>
      <label className="block text-sm font-medium text-slate-200">Additional instructions
        <textarea maxLength={2000} rows={4} value={plan.notes} onChange={e => change('notes', e.target.value)} className="mt-2 w-full rounded-lg border border-slate-600 bg-ink-950 p-3 text-white" placeholder="Pets, family needs, contacts, important supplies…" />
      </label>
      {status && <p aria-live="polite" className="text-sm text-sky-200">{status}</p>}
      <button disabled={saving || loading} className="rounded-xl bg-ocean-400 px-6 py-3 font-semibold text-ink-950 disabled:opacity-50">{saving ? 'Saving…' : loading ? 'Loading…' : 'Save family plan'}</button>
    </form>
    <p className="mt-4 text-xs text-slate-400">For current evacuation orders and shelter instructions, always consult Miami-Dade Emergency Management and the National Weather Service.</p>
  </FeatureShell>
}

function ReportItems({ items, onDelete }: { items: FloodReport[]; onDelete?: (id: number) => void }) {
  if (!items.length) return <p className="mt-4 text-slate-400">No flood incidents recorded yet.</p>
  return <ul className="mt-4 space-y-3">{items.map(report =>
    <li key={report.id} className="rounded-2xl border border-slate-700 bg-ink-950 p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-semibold text-white">{report.address}</p>
          <p className="mt-1 text-xs text-slate-400">Observed {new Date(report.observed_at).toLocaleString()} · {report.verification_status}</p>
        </div>
        {onDelete && <button className="rounded-lg border border-slate-600 px-2 py-1 text-sm text-slate-300 hover:text-white" onClick={() => onDelete(report.id)}>Delete</button>}
      </div>
      <p className="mt-3 whitespace-pre-wrap text-sm text-slate-200">{report.description}</p>
    </li>)}</ul>
}

function usePrivateReports() {
  const [items, setItems] = useState<FloodReport[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [version, setVersion] = useState(0)
  useEffect(() => subscribeAuth(() => { setItems([]); setVersion(v => v + 1) }), [])
  useEffect(() => {
    let active = true
    setLoading(true)
    getFloodReports()
      .then(value => { if (active) { setItems(value); setError('') } })
      .catch(err => { if (active) setError(err instanceof Error ? err.message : 'Cannot load reports') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [version])
  return { items, setItems, error, setError, loading }
}

export function ReportFloodingView() {
  const { items, setItems, error, setError, loading } = usePrivateReports()
  const [address, setAddress] = useState('')
  const [description, setDescription] = useState('')
  const [observed, setObserved] = useState(() => {
    const now = new Date()
    return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
  })
  const [saving, setSaving] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const report = await createFloodReport({ address, description, observed_at: new Date(observed).toISOString() })
      setItems(current => [report, ...current])
      setAddress('')
      setDescription('')
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not save report') }
    finally { setSaving(false) }
  }
  async function remove(id: number) {
    try { await deleteFloodReport(id); setItems(current => current.filter(x => x.id !== id)) }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to delete') }
  }
  return <FeatureShell eyebrow="Personal incident log" title="Report Flooding">
    <p className="mt-3 text-slate-300">Record what you observed for your own reference. Reports remain private and unverified; this is not an emergency dispatch or official incident-reporting service.</p>
    <form onSubmit={e => { void submit(e) }} className="mt-6 space-y-4 rounded-3xl border border-slate-700 bg-ink-900 p-6">
      <label className="block text-sm text-slate-200">Street address
        <input required minLength={5} maxLength={240} value={address} onChange={e => setAddress(e.target.value)} placeholder="111 NW 1st St, Miami, FL 33128" className="mt-2 w-full rounded-lg border border-slate-600 bg-ink-950 p-3 text-white" />
      </label>
      <label className="block text-sm text-slate-200">When did you observe this?
        <input type="datetime-local" required value={observed} onChange={e => setObserved(e.target.value)} className="mt-2 w-full rounded-lg border border-slate-600 bg-ink-950 p-3 text-white" />
      </label>
      <label className="block text-sm text-slate-200">What happened?
        <textarea required minLength={10} maxLength={1500} rows={4} value={description} onChange={e => setDescription(e.target.value)} placeholder="Describe the observed flooding, approximate depth, and any hazards (only what you actually saw)." className="mt-2 w-full rounded-lg border border-slate-600 bg-ink-950 p-3 text-white" />
      </label>
      {error && <p role="alert" className="text-rose-200">{error}</p>}
      <button disabled={saving} className="rounded-xl bg-ocean-400 px-6 py-3 font-semibold text-ink-950 disabled:opacity-50">{saving ? 'Saving…' : 'Save private incident'}</button>
    </form>
    <h2 className="mt-8 text-xl font-semibold text-white">Your reported incidents</h2>
    {loading ? <p className="mt-3 text-slate-400">Loading…</p> : <ReportItems items={items} onDelete={id => { void remove(id) }} />}
  </FeatureShell>
}

export function FloodMemoryView() {
  const { items, error, loading } = usePrivateReports()
  return <FeatureShell eyebrow="Personal history" title="Flood Memory">
    <p className="mt-3 text-slate-300">A private history of flooding you personally recorded. These observations are not official confirmations of historical flooding.</p>
    {error && <p role="alert" className="mt-4 text-rose-200">{error}</p>}
    {loading ? <p className="mt-5 text-slate-400">Loading…</p> : <ReportItems items={items} />}
  </FeatureShell>
}

export function FloodInsuranceView({ locationResult }: { locationResult: AddressLookupResult | null }) {
  const zone = locationResult?.fema_flood_zone.designation
  return <FeatureShell eyebrow="Insurance education" title="Flood Insurance">
    <p className="mt-3 text-slate-300">Understand your mapped flood exposure and explore insurance resources. FloodGuard does not provide insurance quotes, coverage decisions or binding advice.</p>
    <div className="mt-6 rounded-3xl border border-slate-700 bg-ink-900 p-6">
      <h2 className="text-xl font-semibold text-white">Your selected address</h2>
      {locationResult ? <>
        <p className="mt-2 text-slate-300">{locationResult.matched_address}</p>
        <p className="mt-3 text-lg font-semibold text-ocean-300">Mapped FEMA zone: {zone ?? 'Unavailable'}</p>
        <p className="mt-2 text-sm text-slate-400">A FEMA flood-zone designation is not a flood insurance premium or proof of coverage. Flooding can occur outside high-risk mapped zones.</p>
      </> : <p className="mt-3 text-slate-300">Search an address on the Dashboard to show its mapped FEMA flood zone here.</p>}
    </div>
    <div className="mt-5 grid gap-4 sm:grid-cols-2">
      <a className="rounded-2xl border border-ocean-400/30 bg-ink-900 p-5 text-ocean-300 hover:bg-ink-800" href="https://www.floodsmart.gov/" target="_blank" rel="noopener noreferrer">
        <strong className="block text-lg">FloodSmart / NFIP</strong>
        <span className="mt-2 block text-sm text-slate-300">Understand flood policies and find insurance providers.</span>
      </a>
      <a className="rounded-2xl border border-ocean-400/30 bg-ink-900 p-5 text-ocean-300 hover:bg-ink-800" href="https://msc.fema.gov/portal/home" target="_blank" rel="noopener noreferrer">
        <strong className="block text-lg">Official FEMA Flood Map</strong>
        <span className="mt-2 block text-sm text-slate-300">Review federal flood hazard information for a property.</span>
      </a>
    </div>
    <p className="mt-5 text-sm text-slate-400">Ask a licensed insurance professional about deductibles, waiting periods, exclusions, claim documentation and coverage for contents.</p>
  </FeatureShell>
}
