import { useEffect, useState, type FormEvent } from 'react'
import { createSavedLocation, deleteSavedLocation, getSavedLocations, type OwnerType, type SavedLocation } from './api'
import { features, type FeatureId } from './features'

function LocationManager({ ownerType }: { ownerType: OwnerType }) {
  const [locations, setLocations] = useState<SavedLocation[]>([])
  const [label, setLabel] = useState('')
  const [address, setAddress] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const title = ownerType === 'property' ? 'My Property' : 'My Vehicle'
  const helper = ownerType === 'property'
    ? 'Save a home, condo, or property you want to keep flood-ready.'
    : 'Save a parking location so it is ready for future advisory features.'

  async function load() {
    setLoading(true)
    setError('')
    try {
      setLocations(await getSavedLocations(ownerType))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load saved locations.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [ownerType])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const location = await createSavedLocation({ owner_type: ownerType, label, address })
      setLocations((current) => [location, ...current])
      setLabel('')
      setAddress('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to save this location.')
    } finally {
      setSaving(false)
    }
  }

  async function remove(id: number) {
    setError('')
    try {
      await deleteSavedLocation(id)
      setLocations((current) => current.filter((location) => location.id !== id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to remove this location.')
    }
  }

  return (
    <main className="w-full px-5 py-7 sm:px-8 lg:py-10">
      <div className="mx-auto w-full max-w-6xl">
        <p className="mb-3 text-sm font-semibold uppercase tracking-[0.18em] text-tide-400">Saved locations</p>
        <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">{title}</h1>
        <p className="mt-3 max-w-2xl text-slate-300">{helper}</p>

        <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <form
            onSubmit={submit}
            className="rounded-3xl border border-slate-700/80 bg-ink-900 p-6 shadow-[0_20px_60px_rgba(0,0,0,.35)]"
          >
            <h2 className="text-lg font-semibold text-white">Add a location</h2>

            <label className="mt-5 block text-sm font-medium text-slate-200">
              Name
              <input
                value={label}
                onChange={(event) => setLabel(event.target.value)}
                required
                maxLength={80}
                placeholder={ownerType === 'property' ? 'Home' : 'Daily parking'}
                className="mt-2 w-full rounded-xl border border-slate-600 bg-ink-950 px-3 py-2.5 text-white outline-none ring-ocean-400 placeholder:text-slate-500 focus:ring-2"
              />
            </label>

            <label className="mt-4 block text-sm font-medium text-slate-200">
              Miami address or location
              <input
                value={address}
                onChange={(event) => setAddress(event.target.value)}
                required
                maxLength={240}
                placeholder="123 Biscayne Blvd, Miami, FL"
                className="mt-2 w-full rounded-xl border border-slate-600 bg-ink-950 px-3 py-2.5 text-white outline-none ring-ocean-400 placeholder:text-slate-500 focus:ring-2"
              />
            </label>

            <button
              disabled={saving}
              className="mt-5 w-full rounded-xl bg-ocean-400 px-4 py-3 font-semibold text-ink-950 transition hover:bg-ocean-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {saving ? 'Saving…' : `Save ${ownerType === 'property' ? 'property' : 'vehicle location'}`}
            </button>
          </form>

          <section aria-live="polite" className="rounded-3xl border border-slate-700/80 bg-ink-900 p-6">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-white">Your saved locations</h2>
              <button
                onClick={() => void load()}
                className="text-sm font-medium text-ocean-300 hover:text-sky-200"
              >
                Refresh
              </button>
            </div>

            {error
              ? (
                <p className="mt-4 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">
                  {error}
                </p>
                )
              : null}

            {loading
              ? <p className="mt-5 text-slate-400">Loading locations…</p>
              : locations.length === 0
                ? <p className="mt-5 rounded-xl border border-dashed border-slate-700 p-5 text-sm text-slate-400">No {ownerType} locations saved yet.</p>
                : (
                  <ul className="mt-4 space-y-3">
                    {locations.map((location) => (
                      <li
                        key={location.id}
                        className="flex items-start justify-between gap-4 rounded-2xl bg-ink-950 p-4 ring-1 ring-slate-700/70"
                      >
                        <div>
                          <h3 className="font-semibold text-white">{location.label}</h3>
                          <p className="mt-1 text-sm text-slate-400">{location.address}</p>
                        </div>
                        <button
                          onClick={() => void remove(location.id)}
                          className="rounded-lg px-2 py-1 text-sm text-rose-200 hover:bg-rose-400/10 hover:text-rose-100"
                        >
                          Delete
                        </button>
                      </li>
                    ))}
                  </ul>
                  )}
          </section>
        </div>
      </div>
    </main>
  )
}

function Placeholder({ id }: { id: FeatureId }) {
  const feature = features.find((item) => item.id === id)!
  return (
    <main className="w-full px-5 py-7 sm:px-8 lg:py-10">
      <div className="mx-auto w-full max-w-6xl">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-tide-400">FloodGuard Miami</p>
        <h1 className="mt-3 text-3xl font-bold text-white sm:text-4xl">{feature.label}</h1>
        <div className="mt-7 max-w-2xl rounded-3xl border border-slate-700/80 bg-ink-900 p-6">
          <p className="text-lg text-slate-200">{feature.description}</p>
          <p className="mt-4 text-sm leading-6 text-slate-400">
            This Phase 1 dashboard makes every planned FloodGuard feature accessible.
            Data integrations and AI capabilities are intentionally not enabled yet.
          </p>
        </div>
      </div>
    </main>
  )
}

function PremiumCard({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-3xl border border-slate-700/80 bg-[linear-gradient(180deg,rgba(11,23,39,.9),rgba(7,17,29,.9))] p-5 shadow-[0_10px_40px_rgba(0,0,0,.35)]">
      <header>
        <h2 className="text-lg font-semibold text-white sm:text-xl">{title}</h2>
        {subtitle ? <p className="mt-1 text-sm leading-6 text-slate-300">{subtitle}</p> : null}
      </header>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function MapPlaceholder() {
  return (
    <div
      className="relative overflow-hidden rounded-3xl border border-slate-700 bg-[radial-gradient(circle_at_top_right,_rgba(56,189,248,.18),_transparent_45%)]"
      aria-label="Map placeholder"
      role="region"
    >
      <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(56,189,248,.08)_1px,transparent_1px),linear-gradient(0deg,rgba(56,189,248,.08)_1px,transparent_1px)] bg-[size:28px_28px] opacity-40" />
      <div className="relative flex h-64 flex-col justify-between p-5 sm:h-80">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-tide-400">Map container</p>
            <h3 className="mt-2 text-lg font-semibold text-white">Interactive flood-zone map (Phase 2)</h3>
          </div>
          <span className="rounded-full border border-ocean-400/40 bg-ink-900/60 px-3 py-1 text-xs font-semibold text-ocean-300">Leaflet ready</span>
        </div>
        <p className="max-w-xl text-sm leading-6 text-slate-300">
          Phase 1 includes a visual container only—no live flood data is loaded yet.
        </p>
      </div>
    </div>
  )
}

function Dashboard({ setActive }: { setActive: (id: FeatureId) => void }) {
  return (
    <main className="w-full px-5 py-7 sm:px-8 lg:pb-10 lg:pt-0">
      <div className="mx-auto w-full max-w-7xl">
        <div className="grid gap-6">
          {/* Top row: Saved Locations + Ask FloodGuard AI */}
          <section className="grid gap-6 xl:grid-cols-2">
            <div className="rounded-3xl border border-slate-700/80 bg-[radial-gradient(circle_at_top_left,rgba(56,189,248,.18),transparent_45%),linear-gradient(180deg,rgba(11,23,39,.9),rgba(7,17,29,.9))] p-6 sm:p-8">
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-ocean-300">FloodGuard Miami</p>
              <h1 className="mt-3 text-3xl font-bold tracking-tight text-white sm:text-4xl">Saved locations & monitoring</h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-slate-300">
                Your Phase 1 workspace for property and vehicle saved locations—ready for Miami flood intelligence in later phases.
              </p>

              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                <button
                  onClick={() => setActive('property')}
                  className="rounded-xl bg-ocean-400 px-4 py-3 font-semibold text-ink-950 shadow-sm shadow-ocean-400/20 hover:bg-ocean-300"
                >
                  Add a property
                </button>
                <button
                  onClick={() => setActive('vehicle')}
                  className="rounded-xl border border-slate-600 bg-ink-900/50 px-4 py-3 font-semibold text-white hover:bg-white/5"
                >
                  Save vehicle location
                </button>
              </div>

              <div className="mt-3">
                <button
                  onClick={() => setActive('report')}
                  className="w-full rounded-xl border border-slate-600 bg-ink-900/50 px-4 py-3 font-semibold text-white hover:border-ocean-400/40 hover:bg-white/5"
                >
                  Report Flooding
                </button>
              </div>
            </div>

            <section className="rounded-3xl border border-ocean-400/35 bg-[linear-gradient(180deg,rgba(56,189,248,.12),rgba(11,23,39,.9))] p-6 shadow-[0_10px_40px_rgba(0,0,0,.35)] flex flex-col">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-ocean-300">Coming in Phase 3</p>
                  <h2 className="mt-2 text-xl font-bold text-white">Ask FloodGuard AI</h2>
                  <p className="mt-2 text-sm leading-6 text-slate-300">
                    Context-aware assessments grounded in your saved property and vehicle.
                  </p>
                </div>
                <span className="grid h-11 w-11 place-items-center rounded-2xl bg-ocean-400/10 text-2xl text-ocean-300 ring-1 ring-ocean-400/20">
                  ✦
                </span>
              </div>

              <div className="mt-4">
                <button
                  onClick={() => setActive('ai')}
                  className="w-full rounded-2xl bg-ocean-400 px-4 py-3 font-semibold text-ink-950 hover:bg-ocean-300"
                >
                  Open AI section (Phase 3)
                </button>
              </div>

              <div className="mt-4 text-sm text-slate-400">
                Tip: save your property & vehicle to personalize future recommendations.
              </div>
            </section>
          </section>

          {/* Monitoring Map (full width) */}
          <section>
            <PremiumCard title="Monitoring map" subtitle="Phase 2 interactive Leaflet map container (placeholder in Phase 1).">
              <MapPlaceholder />
            </PremiumCard>
          </section>

          {/* Uniform responsive card grid */}
          <section>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <PremiumCard title="My Property" subtitle="Saved addresses that will power future flood context.">
                <button
                  onClick={() => setActive('property')}
                  className="w-full rounded-2xl bg-ink-900 px-4 py-3 text-left font-semibold text-white ring-1 ring-slate-700/80 hover:bg-white/5"
                >
                  Open property saved locations
                </button>
              </PremiumCard>

              <PremiumCard title="My Vehicle" subtitle="Save important parking/pickup points for monitoring.">
                <button
                  onClick={() => setActive('vehicle')}
                  className="w-full rounded-2xl bg-ink-900 px-4 py-3 text-left font-semibold text-white ring-1 ring-slate-700/80 hover:bg-white/5"
                >
                  Open vehicle saved locations
                </button>
              </PremiumCard>

              <PremiumCard title="Tide & Weather" subtitle="Forecasts and alerts become live in Phase 2.">
                <button
                  onClick={() => setActive('weather')}
                  className="w-full rounded-2xl bg-ink-900 px-4 py-3 text-left font-semibold text-white ring-1 ring-slate-700/80 hover:bg-white/5"
                >
                  View tide & weather section
                </button>
              </PremiumCard>

              <PremiumCard title="Report Flooding" subtitle="Photo & incident workflows arrive in Phase 4.">
                <button
                  onClick={() => setActive('report')}
                  className="w-full rounded-2xl bg-ink-900 px-4 py-3 text-left font-semibold text-white ring-1 ring-slate-700/80 hover:bg-white/5"
                >
                  View reporting section
                </button>
              </PremiumCard>
            </div>
          </section>

          {/* Secondary tools section */}
          <section>
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-tide-400">Secondary tools</p>
                <h2 className="mt-2 text-2xl font-bold text-white">More FloodGuard modules</h2>
              </div>
              <span className="text-sm text-slate-400">Phase 1 placeholders</span>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {features
                .filter((f) => !['dashboard', 'property', 'vehicle', 'weather', 'report', 'ai'].includes(f.id))
                .map((feature) => (
                  <button
                    key={feature.id}
                    onClick={() => setActive(feature.id)}
                    className="group rounded-3xl border border-slate-700/80 bg-[linear-gradient(180deg,rgba(11,23,39,.85),rgba(7,17,29,.85))] p-5 text-left transition hover:border-ocean-400/40 hover:bg-white/5 focus-visible:outline"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-semibold text-white">{feature.label}</h3>
                        <p className="mt-2 text-sm leading-6 text-slate-300">{feature.description}</p>
                      </div>
                      <span className="mt-1 grid h-10 w-10 place-items-center rounded-2xl bg-ocean-400/10 text-xl text-ocean-300 ring-1 ring-ocean-400/20 transition group-hover:bg-ocean-400/15">
                        {feature.icon}
                      </span>
                    </div>
                    <span className="mt-3 inline-flex items-center gap-2 text-sm font-semibold text-ocean-300">
                      Open section <span aria-hidden="true">→</span>
                    </span>
                  </button>
                ))}
            </div>
          </section>
        </div>
      </div>
    </main>
  )
}

function App() {
  const [active, setActive] = useState<FeatureId>('dashboard')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  const changeActive = (id: FeatureId) => {
    setActive(id)
    setMobileNavOpen(false)
  }

  return (
    <div className="min-h-screen bg-ink-950">
      <header className="sticky top-0 z-20 border-b border-slate-800/80 bg-ink-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8">
          <button onClick={() => changeActive('dashboard')} className="flex items-center gap-3 text-left" aria-label="Go to Dashboard">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-ocean-400 to-tide-400 font-black text-ink-950">FG</span>
            <span>
              <span className="block font-bold text-white">FloodGuard</span>
              <span className="block text-xs text-tide-400">MIAMI</span>
            </span>
          </button>

          <button
            className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-white lg:hidden"
            onClick={() => setMobileNavOpen(!mobileNavOpen)}
            aria-expanded={mobileNavOpen}
            aria-controls="mobile-nav"
          >
            Menu
          </button>

        </div>

        {mobileNavOpen ? (
          <nav id="mobile-nav" className="border-t border-slate-800 px-5 py-3 lg:hidden" aria-label="Mobile navigation">
            <div className="grid gap-2">
              {features.map((item) => (
                <button
                  key={item.id}
                  onClick={() => changeActive(item.id)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm transition focus-visible:outline ${
                    active === item.id ? 'bg-sky-400/15 text-ocean-300' : 'text-slate-200 hover:bg-white/5'
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </nav>
        ) : null}
      </header>


      <div className="mx-auto w-full max-w-[1500px] px-0 lg:px-5">
        <div className="grid min-h-[calc(100vh-140px)] grid-cols-1 gap-6 lg:grid-cols-[240px_minmax(0,1fr)] lg:gap-6 overflow-x-hidden">
          <aside className="hidden lg:block">
            <div className="sticky top-0 rounded-3xl border border-slate-700/80 bg-[linear-gradient(180deg,rgba(11,23,39,.85),rgba(7,17,29,.85))] p-4" style={{width: 240}}>
              <p className="px-2 text-xs font-semibold uppercase tracking-[0.18em] text-ocean-300">Navigation</p>
              <nav className="mt-3 grid gap-3 px-2" aria-label="Sidebar navigation">
                {features.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => changeActive(item.id)}
                    className={`flex items-center justify-between gap-3 rounded-2xl px-3 py-3 text-left transition focus-visible:outline ${
                      active === item.id
                        ? 'bg-sky-400/15 text-white ring-1 ring-ocean-400/30'
                        : 'text-slate-200 hover:bg-white/5 hover:text-white'
                    }`}>
                    <span className="font-semibold">{item.label}</span>
                    <span className="grid h-8 w-8 place-items-center rounded-xl bg-ocean-400/10 text-sm text-ocean-300 ring-1 ring-ocean-400/20">{item.icon}</span>
                  </button>
                ))}
              </nav>
            </div>
          </aside>

          <main className="min-h-[60vh]">
            {active === 'dashboard'
              ? <Dashboard setActive={changeActive} />
              : active === 'property' || active === 'vehicle'
                ? <LocationManager ownerType={active} />
                : <Placeholder id={active} />}

            <footer className="mt-2 mb-6 w-full px-5 pb-6 text-sm text-slate-500 sm:px-8 lg:px-0">
              FloodGuard Miami · Preparedness information, not an emergency service.
            </footer>
          </main>
        </div>
      </div>
    </div>
  )
}

export default App
