import { useEffect, useRef, useState, type FormEvent } from 'react'
import { MapContainer, Marker, Popup, TileLayer, ZoomControl } from 'react-leaflet'
import L from 'leaflet'
import { createSavedLocation, deleteSavedLocation, fetchFEMAOverlay, getSavedLocations, lookupAddress, lookupTides, lookupWeather, type AddressLookupResult, type OwnerType, type SavedLocation, type TidesResult, type WeatherResult } from './api'
import { features, type FeatureId } from './features'

// Fix Leaflet default marker icon path for Vite bundling
const defaultIcon = L.icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
})
L.Marker.prototype.options.icon = defaultIcon

const MIAMI_CENTER: [number, number] = [25.7617, -80.1918]

// Accessible, distinct colors for the most common FEMA Special Flood Hazard Area zones.
const FEMA_ZONE_COLORS: Record<string, string> = {
  AE: '#ef4444', // red
  VE: '#f97316', // orange
  AH: '#eab308', // yellow
  AO: '#a855f7', // purple
  A: '#22c55e',  // green
  X: '#64748b',  // slate
  D: '#94a3b8',  // light slate
}

function femaZoneColor(fzone: string | null): string {
  if (!fzone) return FEMA_ZONE_COLORS.X
  const normalized = fzone.trim().toUpperCase()
  return FEMA_ZONE_COLORS[normalized] ?? '#f59e0b'
}

function formatFEMAAttribute(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'number') return Number.isInteger(value) ? value.toString() : value.toFixed(2)
  return String(value)
}

interface MapMarkerData {
  id: string
  lat: number
  lon: number
  label: string
  address: string
  femaZone: string | null
}

function FEMAOverlayLayer({ map, enabled }: { map: L.Map; enabled: boolean }) {
  const [overlay, setOverlay] = useState<L.GeoJSON | null>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'ok' | 'incomplete' | 'error'>('idle')
  const [lastBoundsKey, setLastBoundsKey] = useState<string>('')
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!enabled) {
      if (overlay) {
        map.removeLayer(overlay)
        setOverlay(null)
      }
      setStatus('idle')
      return
    }

    const zoom = map.getZoom()
    if (zoom < 11) {
      setStatus('error')
      return
    }

    const bounds = map.getBounds()
    const sw = bounds.getSouthWest()
    const ne = bounds.getNorthEast()
    const boundsKey = `${sw.lat.toFixed(3)},${sw.lng.toFixed(3)}|${ne.lat.toFixed(3)},${ne.lng.toFixed(3)}`
    if (boundsKey === lastBoundsKey && status === 'ok') return

    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller

    async function load() {
      setStatus('loading')
      try {
        const result = await fetchFEMAOverlay({
          sw_lat: sw.lat,
          sw_lon: sw.lng,
          ne_lat: ne.lat,
          ne_lon: ne.lng,
        })
        if (controller.signal.aborted) return

        const geoJson = L.geoJSON(result.features as unknown as GeoJSON.FeatureCollection, {
          style: (feature) => {
            const props = (feature?.properties ?? {}) as Record<string, unknown>
            const fzone = String(props.FZONE ?? '')
            return {
              color: femaZoneColor(fzone),
              weight: 1.5,
              opacity: 0.85,
              fillColor: femaZoneColor(fzone),
              fillOpacity: 0.35,
            }
          },
          onEachFeature: (feature, layer) => {
            const props = (feature.properties ?? {}) as Record<string, unknown>
            const popup = L.popup({ className: 'fema-popup' }).setContent(`
              <div class="text-sm">
                <p class="font-semibold text-white mb-1">FEMA Flood Zone: ${formatFEMAAttribute(props.FZONE)}</p>
                <p class="text-slate-300">Zone subtype: ${formatFEMAAttribute(props.ZONESUBTY)}</p>
                <p class="text-slate-300">Elevation: ${formatFEMAAttribute(props.ELEV)} ft</p>
                <p class="text-slate-500 mt-2 text-xs">Mapped flood hazard, not real-time flooding.</p>
              </div>
            `)
            layer.bindPopup(popup)
          },
        })
        geoJson.addTo(map)
        if (overlay) map.removeLayer(overlay)
        setOverlay(geoJson)
        setLastBoundsKey(boundsKey)
        setStatus(result.status === 'incomplete' ? 'incomplete' : 'ok')
      } catch (err) {
        if (controller.signal.aborted) return
        setStatus('error')
      }
    }

    void load()

    return () => {
      controller.abort()
    }
  }, [enabled, map])

  if (!enabled) return null

  return (
    <div className="absolute bottom-3 left-3 z-[1000] flex max-w-xs flex-col gap-2">
      <div className="rounded-xl border border-slate-700 bg-ink-950/95 p-3 shadow-lg">
        <p className="text-xs font-semibold uppercase tracking-wider text-tide-400">FEMA zones</p>
        <ul className="mt-2 space-y-1 text-xs text-slate-300">
          <li className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: FEMA_ZONE_COLORS.AE }} /> AE — 1% annual chance</li>
          <li className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: FEMA_ZONE_COLORS.VE }} /> VE — coastal 1% chance</li>
          <li className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: FEMA_ZONE_COLORS.AH }} /> AH — shallow flooding</li>
          <li className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: FEMA_ZONE_COLORS.AO }} /> AO — sheet flow</li>
          <li className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: FEMA_ZONE_COLORS.A }} /> A — no BFE determined</li>
          <li className="flex items-center gap-2"><span className="inline-block h-3 w-3 rounded-sm" style={{ backgroundColor: FEMA_ZONE_COLORS.X }} /> X — minimal/low risk</li>
        </ul>
        <p className="mt-2 text-[10px] leading-tight text-slate-500">Source: Miami-Dade ArcGIS FEMA Flood Zones. Click a polygon for official attributes.</p>
      </div>
      {status === 'loading' ? <p className="rounded-lg bg-ink-950/90 px-3 py-1 text-xs text-slate-300">Loading overlay…</p> : null}
      {status === 'incomplete' ? <p className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-xs text-amber-200">Coverage incomplete — zoom in to load more zones.</p> : null}
      {status === 'error' ? <p className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-1 text-xs text-rose-200">Overlay unavailable. Zoom in or try again.</p> : null}
    </div>
  )
}

function FloodGuardMap({ searchedResult, savedLocations }: { searchedResult: AddressLookupResult | null; savedLocations: SavedLocation[] }) {
  const [map, setMap] = useState<L.Map | null>(null)
  const [overlayEnabled, setOverlayEnabled] = useState(false)
  const markers: MapMarkerData[] = []

  if (searchedResult) {
    markers.push({
      id: 'searched',
      lat: searchedResult.coordinates.latitude,
      lon: searchedResult.coordinates.longitude,
      label: 'Searched address',
      address: searchedResult.matched_address,
      femaZone: searchedResult.fema_flood_zone.designation,
    })
  }

  // Render saved locations only when they carry usable coordinates; no geocoding here.
  for (const location of savedLocations) {
    if (location.latitude == null || location.longitude == null) continue
    markers.push({
      id: `saved-${location.id}`,
      lat: location.latitude,
      lon: location.longitude,
      label: location.owner_type === 'property' ? `Saved property · ${location.label}` : `Saved vehicle · ${location.label}`,
      address: location.address,
      femaZone: null,
    })
  }

  return (
    <div
      className="relative overflow-hidden rounded-2xl border border-slate-700"
      aria-label="Interactive flood-zone map"
      role="region"
    >
      <div className="absolute right-3 top-3 z-[1000]">
        <button
          type="button"
          onClick={() => setOverlayEnabled((v) => !v)}
          className={`rounded-xl px-3 py-2 text-xs font-semibold shadow-lg ring-1 ${overlayEnabled ? 'bg-ocean-400 text-ink-950 ring-ocean-300' : 'bg-ink-950/95 text-white ring-slate-600'}`}
          aria-pressed={overlayEnabled}
        >
          {overlayEnabled ? 'Hide FEMA overlay' : 'Show FEMA overlay'}
        </button>
      </div>
      <MapContainer
        center={MIAMI_CENTER}
        zoom={12}
        scrollWheelZoom={false}
        zoomControl={false}
        className="h-80 w-full sm:h-96"
        ref={setMap}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ZoomControl position="topright" />
        {markers.map((marker) => (
          <Marker key={marker.id} position={[marker.lat, marker.lon]}>
            <Popup>
              <div>
                <p className="font-semibold text-white">{marker.label}</p>
                <p className="mt-1 text-slate-300">{marker.address}</p>
                <p className="mt-2 text-slate-400">
                  FEMA zone: <span className="font-semibold text-ocean-300">{marker.femaZone ?? 'No mapped feature'}</span>
                </p>
                <p className="mt-1 text-xs text-slate-500">Not a real-time street-flood forecast.</p>
              </div>
            </Popup>
          </Marker>
        ))}
        {map ? <FEMAOverlayLayer map={map} enabled={overlayEnabled} /> : null}
      </MapContainer>
    </div>
  )
}

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

function useWeather(coords: { latitude: number; longitude: number } | null) {
  const [weather, setWeather] = useState<WeatherResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!coords) {
      setWeather(null)
      return
    }
    let cancelled = false
    setLoading(true)
    setError('')
    lookupWeather(coords.latitude, coords.longitude)
      .then((result) => { if (!cancelled) setWeather(result) })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : 'Weather data unavailable.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [coords?.latitude, coords?.longitude])

  return { weather, loading, error }
}

function WeatherSummaryCard({ onOpen }: { onOpen: () => void }) {
  const [lookupResult, setLookupResult] = useState<AddressLookupResult | null>(null)
  const { weather, loading, error } = useWeather(lookupResult?.coordinates ?? null)

  return (
    <PremiumCard title="Tide & Weather" subtitle="Official NWS hourly forecast and active alerts for a Miami address.">
      <div className="flex flex-col gap-3">
        <form onSubmit={async (event) => {
          event.preventDefault()
          const input = (event.currentTarget.elements.namedItem('weather-address') as HTMLInputElement).value.trim()
          if (!input) return
          try {
            setLookupResult(await lookupAddress(input))
          } catch (err) {
            // Surface error via weather state below if coordinates missing
          }
        }} className="flex flex-col gap-2">
          <input
            name="weather-address"
            defaultValue="111 NW 1st St, Miami, FL 33128"
            minLength={3}
            maxLength={240}
            placeholder="111 NW 1st St, Miami, FL 33128"
            aria-label="Address for weather"
            className="min-w-0 rounded-xl border border-slate-600 bg-ink-950 px-3 py-2.5 text-white outline-none placeholder:text-slate-500 focus:ring-2 focus:ring-ocean-400"
          />
          <button type="submit" className="rounded-xl bg-ocean-400 px-4 py-2.5 font-semibold text-ink-950 hover:bg-ocean-300">
            Load forecast
          </button>
        </form>

        {!lookupResult && !loading && !error ? (
          <p className="text-sm text-slate-400">Enter an address above to load the official forecast.</p>
        ) : null}

        {loading ? <p className="text-sm text-slate-400">Loading NWS forecast…</p> : null}
        {error ? <p className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-2 text-sm text-rose-200">{error}</p> : null}

        {weather ? (
          <div className="rounded-2xl bg-ink-950 p-3 ring-1 ring-slate-700/80">
            <p className="text-sm text-slate-400">Status</p>
            <p className={`font-semibold ${weather.status === 'flood_alerts' ? 'text-rose-300' : weather.status === 'unavailable' || weather.status === 'stale' ? 'text-amber-300' : 'text-emerald-300'}`}>
              {weather.status === 'flood_alerts' ? 'Flood-related alerts active' : weather.status === 'no_alerts' ? 'No active alerts' : weather.status === 'unavailable' ? 'Forecast unavailable' : 'Data stale'}
            </p>
            {weather.hourly_periods.length > 0 ? (
              <>
                <p className="mt-2 text-sm text-slate-400">Next hour</p>
                <p className="text-sm text-white">{weather.hourly_periods[0].short_forecast} — {weather.hourly_periods[0].temperature}°{weather.hourly_periods[0].temperature_unit}</p>
              </>
            ) : null}
            <p className="mt-2 text-xs text-slate-500">Source: {weather.source}</p>
          </div>
        ) : null}
      </div>
      <button
        onClick={onOpen}
        className="mt-4 w-full rounded-2xl bg-ink-900 px-4 py-3 text-left font-semibold text-white ring-1 ring-slate-700/80 hover:bg-white/5"
      >
        View full weather section
      </button>
    </PremiumCard>
  )
}

function useTides() {
  const [tides, setTides] = useState<TidesResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  function load() {
    setLoading(true)
    setError('')
    lookupTides()
      .then(setTides)
      .catch((err) => setError(err instanceof Error ? err.message : 'Tide data unavailable.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { void load() }, [])

  return { tides, loading, error, reload: load }
}

function TidesPanel({ showDetail }: { showDetail?: boolean }) {
  const { tides, loading, error, reload } = useTides()

  return (
    <section className="rounded-3xl border border-slate-700/80 bg-ink-900 p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-white">NOAA tides · Virginia Key</h2>
        <button onClick={() => reload()} className="text-sm font-medium text-ocean-300 hover:text-sky-200">Refresh</button>
      </div>
      <p className="mt-1 text-sm text-slate-400">Station 8723214 · MLLW · feet · NOAA CO-OPS</p>

      {loading ? <p className="mt-5 text-slate-400">Loading tide data…</p> : null}
      {error ? <p className="mt-4 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</p> : null}

      {tides ? (
        <div className="mt-4 grid gap-4">
          {tides.status === 'unavailable' ? (
            <p className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">{tides.message ?? 'NOAA tide data is unavailable.'}</p>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-2xl bg-ink-950 p-3 ring-1 ring-slate-700/70">
              <p className="text-sm text-slate-400">Latest observed water level</p>
              {tides.current_water_level ? (
                <>
                  <p className="text-2xl font-bold text-white">{tides.current_water_level.value.toFixed(2)} <span className="text-base font-normal">{tides.current_water_level.units} {tides.current_water_level.datum}</span></p>
                  <p className="text-xs text-slate-500">{new Date(tides.current_water_level.timestamp).toLocaleString()}</p>
                </>
              ) : (
                <p className="text-sm text-slate-400">No current observation available.</p>
              )}
            </div>

            <div className="rounded-2xl bg-ink-950 p-3 ring-1 ring-slate-700/70">
              <p className="text-sm text-slate-400">Next predicted high tide</p>
              {tides.next_high_tide ? (
                <>
                  <p className="text-2xl font-bold text-white">{tides.next_high_tide.value.toFixed(2)} <span className="text-base font-normal">{tides.next_high_tide.units}</span></p>
                  <p className="text-xs text-slate-500">{new Date(tides.next_high_tide.timestamp).toLocaleString()}</p>
                </>
              ) : (
                <p className="text-sm text-slate-400">No upcoming high tide in forecast.</p>
              )}
            </div>
          </div>

          {tides.comparison ? (
            <div className="rounded-2xl bg-ink-950 p-3 ring-1 ring-slate-700/70">
              <p className="text-sm text-slate-400">Observation vs prediction</p>
              <p className="text-sm text-white">Observed {tides.comparison.observed_value.toFixed(2)} ft · Predicted {tides.comparison.predicted_value.toFixed(2)} ft · Difference <span className={tides.comparison.difference > 0.5 ? 'text-rose-300' : 'text-emerald-300'}>{tides.comparison.difference > 0 ? '+' : ''}{tides.comparison.difference.toFixed(2)} ft</span></p>
              <p className="text-xs text-slate-500">Compared at {new Date(tides.comparison.timestamp).toLocaleString()}</p>
            </div>
          ) : null}

          <div className={`rounded-2xl p-3 ring-1 ${tides.king_tide_watch.active ? 'bg-rose-500/10 ring-rose-500/40' : 'bg-emerald-500/5 ring-emerald-500/30'}`}>
            <p className={`font-semibold ${tides.king_tide_watch.active ? 'text-rose-200' : 'text-emerald-200'}`}>King Tide Watch</p>
            <p className="text-sm text-slate-300">{tides.king_tide_watch.message}</p>
            {tides.king_tide_watch.next_high_tides_above_threshold.length > 0 ? (
              <ul className="mt-2 space-y-1">
                {tides.king_tide_watch.next_high_tides_above_threshold.map((t) => (
                  <li key={t.timestamp} className="text-sm text-white">{t.value.toFixed(2)} ft · {new Date(t.timestamp).toLocaleString()}</li>
                ))}
              </ul>
            ) : null}
            <p className="mt-2 text-xs text-slate-500">Threshold: {tides.king_tide_watch.threshold_value} {tides.king_tide_watch.threshold_units}. {tides.king_tide_watch.threshold_source}</p>
          </div>

          {showDetail && tides.upcoming_high_tides.length > 0 ? (
            <div>
              <p className="text-sm font-semibold text-white">Upcoming high tides</p>
              <ul className="mt-2 space-y-1">
                {tides.upcoming_high_tides.map((t) => (
                  <li key={t.timestamp} className="text-sm text-slate-300">{t.value.toFixed(2)} ft · {new Date(t.timestamp).toLocaleString()}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-2">
            {Object.entries(tides.source_urls).map(([label, url]) => (
              <a key={label} href={url} target="_blank" rel="noreferrer" className="text-sm font-semibold text-ocean-300 hover:text-sky-200">NOAA {label} source →</a>
            ))}
          </div>
          <p className="text-xs text-slate-500">Retrieved {new Date(tides.retrieved_at).toLocaleString()}</p>
        </div>
      ) : null}
    </section>
  )
}

function WeatherDetail({ result }: { result: AddressLookupResult }) {
  const { weather, loading, error } = useWeather(result.coordinates)

  return (
    <main className="w-full px-5 py-7 sm:px-8 lg:py-10">
      <div className="mx-auto w-full max-w-6xl">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-tide-400">FloodGuard Miami</p>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-white sm:text-4xl">Tide & Weather</h1>
        <p className="mt-3 max-w-2xl text-slate-300">
          Official NWS forecast and NOAA CO-OPS tides for {result.matched_address}.
        </p>

        {loading ? <p className="mt-6 text-slate-400">Loading NWS forecast…</p> : null}
        {error ? <p className="mt-6 rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</p> : null}

        {weather ? (
          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <section className="rounded-3xl border border-slate-700/80 bg-ink-900 p-6">
              <h2 className="text-lg font-semibold text-white">Hourly forecast</h2>
              {weather.hourly_periods.length === 0 ? (
                <p className="mt-3 text-sm text-slate-400">No forecast periods returned.</p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {weather.hourly_periods.map((period) => (
                    <li key={period.number} className="rounded-2xl bg-ink-950 p-3 ring-1 ring-slate-700/70">
                      <p className="font-semibold text-white">{period.short_forecast}</p>
                      <p className="text-sm text-slate-300">{period.temperature}°{period.temperature_unit} · Wind {period.wind_speed} {period.wind_direction} · Rain chance {period.precipitation_chance ?? 0}%</p>
                      <p className="text-xs text-slate-500">{new Date(period.start_time).toLocaleString()}</p>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="rounded-3xl border border-slate-700/80 bg-ink-900 p-6">
              <h2 className="text-lg font-semibold text-white">Active alerts</h2>
              {weather.active_alerts.length === 0 ? (
                <p className="mt-3 text-sm text-emerald-300">No active weather alerts for this location.</p>
              ) : (
                <ul className="mt-3 space-y-3">
                  {weather.active_alerts.map((alert) => (
                    <li key={alert.id} className={`rounded-2xl p-3 ring-1 ${alert.is_flood_related ? 'bg-rose-500/10 ring-rose-500/40' : 'bg-ink-950 ring-slate-700/70'}`}>
                      <p className={`font-semibold ${alert.is_flood_related ? 'text-rose-200' : 'text-white'}`}>{alert.event}{alert.is_flood_related ? ' — flood-related' : ''}</p>
                      <p className="mt-1 text-sm text-slate-300">{alert.headline}</p>
                      <p className="mt-2 text-xs text-slate-400">Severity: {alert.severity ?? 'unknown'} · Urgency: {alert.urgency ?? 'unknown'}</p>
                      <a href={alert.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm font-semibold text-ocean-300 hover:text-sky-200">Open alert source →</a>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-4 text-xs text-slate-500">Source: {weather.source} · Retrieved {new Date(weather.retrieved_at).toLocaleString()}</p>
            </section>
          </div>
        ) : null}

        <div className="mt-6">
          <TidesPanel showDetail />
        </div>
      </div>
    </main>
  )
}

function AddressSearch({ onResult }: { onResult?: (result: AddressLookupResult) => void }) {
  const [address, setAddress] = useState('')
  const [result, setResult] = useState<AddressLookupResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setLoading(true)
    setError('')
    setResult(null)
    try {
      const found = await lookupAddress(address.trim())
      setResult(found)
      onResult?.(found)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to look up this address.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <PremiumCard title="Check a Miami address" subtitle="Look up the mapped FEMA flood-zone designation for a geocoded address.">
      <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row">
        <input
          value={address}
          onChange={(event) => setAddress(event.target.value)}
          required
          minLength={3}
          maxLength={240}
          placeholder="111 NW 1st St, Miami, FL 33128"
          aria-label="Address to look up"
          className="min-w-0 flex-1 rounded-xl border border-slate-600 bg-ink-950 px-3 py-3 text-white outline-none placeholder:text-slate-500 focus:ring-2 focus:ring-ocean-400"
        />
        <button disabled={loading} className="rounded-xl bg-ocean-400 px-5 py-3 font-semibold text-ink-950 hover:bg-ocean-300 disabled:cursor-not-allowed disabled:opacity-60">
          {loading ? 'Checking…' : 'Check zone'}
        </button>
      </form>

      {error ? <p role="alert" className="mt-4 rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</p> : null}
      {result ? (
        <div className="mt-4 rounded-2xl bg-ink-950 p-4 ring-1 ring-slate-700/80" aria-live="polite">
          <p className="text-sm text-slate-400">Matched address</p>
          <p className="mt-1 font-semibold text-white">{result.matched_address}</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div>
              <p className="text-sm text-slate-400">FEMA flood zone</p>
              <p className="mt-1 text-2xl font-bold text-ocean-300">{result.fema_flood_zone.designation ?? 'No mapped feature returned'}</p>
            </div>
            <div>
              <p className="text-sm text-slate-400">Coordinates</p>
              <p className="mt-1 text-sm text-slate-200">{result.coordinates.latitude.toFixed(6)}, {result.coordinates.longitude.toFixed(6)}</p>
            </div>
          </div>
          <p className="mt-4 text-sm leading-6 text-slate-300">This is a mapped FEMA designation, not a real-time street-flood forecast or risk score.</p>
          <a href={result.source_url} target="_blank" rel="noreferrer" className="mt-3 inline-block text-sm font-semibold text-ocean-300 hover:text-sky-200">Open official source →</a>
        </div>
      ) : null}
    </PremiumCard>
  )
}

function Dashboard({ setActive, onAddressResult }: { setActive: (id: FeatureId) => void; onAddressResult: (result: AddressLookupResult) => void }) {
  const [mapResult, setMapResult] = useState<AddressLookupResult | null>(null)
  const [savedLocations, setSavedLocations] = useState<SavedLocation[]>([])

  useEffect(() => {
    let cancelled = false
    Promise.all([
      getSavedLocations('property').catch(() => [] as SavedLocation[]),
      getSavedLocations('vehicle').catch(() => [] as SavedLocation[]),
    ]).then(([properties, vehicles]) => {
      if (!cancelled) setSavedLocations([...properties, ...vehicles])
    })
    return () => { cancelled = true }
  }, [])

  function handleAddressResult(result: AddressLookupResult) {
    setMapResult(result)
    onAddressResult(result)
  }

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

          {/* Public Phase 2.1 address lookup */}
          <section>
            <AddressSearch onResult={handleAddressResult} />
          </section>

          {/* Monitoring Map (full width) */}
          <section>
            <PremiumCard title="Monitoring map" subtitle="Interactive Leaflet map of Miami with searched addresses and FEMA flood-zone designations.">
              <FloodGuardMap searchedResult={mapResult} savedLocations={savedLocations} />
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

              <WeatherSummaryCard onOpen={() => setActive('weather')} />

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

function WeatherPlaceholder() {
  return (
    <main className="w-full px-5 py-7 sm:px-8 lg:py-10">
      <div className="mx-auto w-full max-w-6xl">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-tide-400">FloodGuard Miami</p>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-white sm:text-4xl">Tide & Weather</h1>
        <div className="mt-7 max-w-2xl rounded-3xl border border-slate-700/80 bg-ink-900 p-6">
          <p className="text-lg text-slate-200">Use the address search on the dashboard to load the official NWS forecast for a Miami-Dade location.</p>
          <p className="mt-4 text-sm leading-6 text-slate-400">Weather data is tied to a verified address from the Phase 2.1 address lookup.</p>
        </div>
      </div>
    </main>
  )
}

function KingTideWatchView() {
  return (
    <main className="w-full px-5 py-7 sm:px-8 lg:py-10">
      <div className="mx-auto w-full max-w-6xl">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-tide-400">FloodGuard Miami</p>
        <h1 className="mt-3 text-3xl font-bold tracking-tight text-white sm:text-4xl">King Tide Watch</h1>
        <p className="mt-3 max-w-3xl text-slate-300">
          Elevated predicted tides at Virginia Key (NOAA CO-OPS station 8723214), measured against a documented local
          reference threshold. These are tide predictions — they indicate elevated tide conditions, not confirmed street
          flooding, and are never compared directly with FEMA flood elevations.
        </p>
        <div className="mt-6">
          <TidesPanel showDetail />
        </div>
      </div>
    </main>
  )
}

function App() {
  const [active, setActive] = useState<FeatureId>('dashboard')
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [addressSearchResult, setAddressSearchResult] = useState<AddressLookupResult | null>(null)

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
              ? <Dashboard setActive={changeActive} onAddressResult={setAddressSearchResult} />
              : active === 'property' || active === 'vehicle'
                ? <LocationManager ownerType={active} />
                : active === 'weather'
                  ? addressSearchResult
                    ? <WeatherDetail result={addressSearchResult} />
                    : <WeatherPlaceholder />
                  : active === 'king-tide'
                    ? <KingTideWatchView />
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
