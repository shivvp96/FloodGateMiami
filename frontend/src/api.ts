import { privateHeaders } from './auth'

export type OwnerType = 'property' | 'vehicle'

export interface SavedLocation {
  id: number
  owner_type: OwnerType
  label: string
  address: string
  created_at: string
  // Optional: present only if the backend starts returning geocoded coordinates.
  latitude?: number | null
  longitude?: number | null
}

export interface AddressLookupResult {
  request_id: string
  matched_address: string
  coordinates: { latitude: number; longitude: number }
  fema_flood_zone: {
    designation: string | null
    zone_type: string | null
    raw_attributes: Record<string, string>
  }
  source_url: string
  retrieved_at: string
  available_zone_attributes: Record<string, string>
}

export interface FEMAOverlayFeature {
  type: string
  geometry: Record<string, unknown>
  properties: Record<string, unknown>
  id?: number | null
}

export interface FEMAOverlayResult {
  status: 'ok' | 'incomplete' | 'unavailable'
  source_url: string
  retrieved_at: string
  features: FEMAOverlayFeature[]
  total_returned: number
  exceeded_transfer_limit: boolean
  message: string | null
}

export interface HourlyForecastPeriod {
  number: number
  start_time: string
  end_time: string
  is_daytime: boolean
  temperature: number | null
  temperature_unit: string | null
  short_forecast: string | null
  detailed_forecast: string | null
  wind_speed: string | null
  wind_direction: string | null
  precipitation_chance: number | null
}

export interface WeatherAlert {
  id: string
  event: string
  headline: string
  severity: string | null
  urgency: string | null
  certainty: string | null
  effective: string | null
  expires: string | null
  description: string
  instruction: string | null
  sender_name: string | null
  area_desc: string | null
  is_flood_related: boolean
  source_url: string
}

export interface WeatherResult {
  status: 'ok' | 'no_alerts' | 'flood_alerts' | 'unavailable' | 'stale'
  coordinates: { latitude: number; longitude: number }
  forecast_url: string | null
  hourly_periods: HourlyForecastPeriod[]
  active_alerts: WeatherAlert[]
  flood_alert_count: number
  source: string
  retrieved_at: string
  message: string | null
}

export interface TidePrediction {
  timestamp: string
  value: number
  type: string
  units: string
}

export interface TideComparison {
  observed_value: number
  predicted_value: number
  difference: number
  units: string
  timestamp: string
}

export interface KingTideWatch {
  active: boolean
  threshold_value: number
  threshold_units: string
  threshold_source: string
  message: string
  next_high_tides_above_threshold: TidePrediction[]
}

export interface TidesResult {
  status: 'ok' | 'predictions_only' | 'observations_only' | 'unavailable'
  station_id: string
  station_name: string | null
  current_water_level: { timestamp: string; value: number; units: string; datum: string } | null
  next_high_tide: TidePrediction | null
  upcoming_high_tides: TidePrediction[]
  comparison: TideComparison | null
  king_tide_watch: KingTideWatch
  source_urls: Record<string, string>
  retrieved_at: string
  message: string | null
}

export interface AskFloodGuardGrounding {
  fema: {
    designation: string | null
    zone_type: string | null
    source: string
  } | { error: string } | null
  weather: {
    status: string
    flood_alert_count: number
    active_alerts: Array<{ event: string; headline: string | null; severity: string | null; area: string | null }>
    hourly_forecast_next_12h: Array<{ time: string; temp_f: number | null; forecast: string | null; precip_chance: number | null }>
    message: string | null
  } | { error: string } | null
  tides: {
    status: string
    current_water_level: { timestamp: string; value: number; units: string } | null
    next_high_tide: { timestamp: string; value: number; units: string } | null
    king_tide_watch: { active: boolean; next_high_tides_above_threshold: unknown[] }
    message: string | null
  } | { error: string } | null
}

export interface AskFloodGuardResult {
  status: 'ok' | 'unavailable'
  answer: string
  question: string
  grounding: AskFloodGuardGrounding
  model: string | null
  retrieved_at: string
  message: string | null
}

export interface MoveCarRiskFactor {
  kind: 'fema_zone' | 'flood_alert' | 'high_tide' | 'king_tide'
  detail: string
  source: string
}

export interface MoveCarCandidate {
  location_id: number
  label: string
  address: string
  latitude: number
  longitude: number
  fema_zone: string | null
  note: string
}

export interface MoveMyCarResult {
  status: 'ok' | 'no_location' | 'insufficient_data'
  location_id: number
  vehicle_label: string | null
  recommendation: 'consider_moving' | 'stay_parked' | 'no_recommendation'
  risk_factors: MoveCarRiskFactor[]
  candidates: MoveCarCandidate[]
  disclaimer: string
  retrieved_at: string
  message: string | null
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const baseUrl = `${apiBaseUrl}/api/v1/saved-locations/`
const addressLookupUrl = `${apiBaseUrl}/api/v1/address/lookup`
const addressOverlayUrl = `${apiBaseUrl}/api/v1/address/overlay`
const weatherLookupUrl = `${apiBaseUrl}/api/v1/weather/lookup`
const tidesLookupUrl = `${apiBaseUrl}/api/v1/tides/lookup`

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null
    if (response.status === 401 || response.status === 503 && payload?.detail?.includes('authentication not configured')) {
      throw new SavedLocationsAuthError(payload?.detail)
    }
    throw new Error(payload?.detail || `Request failed (${response.status})`)
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>
}

/** Saved locations are protected by a server-side API key (SAVED_LOCATIONS_API_KEY).
 * The browser never holds that key, so in production these calls fail closed and the
 * UI shows this blocker instead of a generic error. Fix = deployment configuration,
 * not frontend code. */
export class SavedLocationsAuthError extends Error {
  constructor(detail?: string) {
    super(detail?.includes('not configured')
      ? 'Account login is not configured yet on the server.'
      : 'Please sign in to manage private properties and vehicles.')
    this.name = 'SavedLocationsAuthError'
  }
}

export async function getSavedLocations(ownerType: OwnerType): Promise<SavedLocation[]> {
  return readResponse<SavedLocation[]>(await fetch(`${baseUrl}?owner_type=${ownerType}`, { headers: await privateHeaders() }))
}

export async function createSavedLocation(location: Omit<SavedLocation, 'id' | 'created_at'>): Promise<SavedLocation> {
  return readResponse<SavedLocation>(await fetch(baseUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...await privateHeaders() },
    body: JSON.stringify(location),
  }))
}

export async function deleteSavedLocation(id: number): Promise<void> {
  return readResponse<void>(await fetch(`${baseUrl}${id}`, { method: 'DELETE', headers: await privateHeaders() }))
}

export async function lookupAddress(address: string): Promise<AddressLookupResult> {
  return readResponse<AddressLookupResult>(await fetch(`${addressLookupUrl}?address=${encodeURIComponent(address)}`))
}

export async function fetchFEMAOverlay(bounds: { sw_lat: number; sw_lon: number; ne_lat: number; ne_lon: number }): Promise<FEMAOverlayResult> {
  return readResponse<FEMAOverlayResult>(await fetch(
    `${addressOverlayUrl}?sw_lat=${bounds.sw_lat}&sw_lon=${bounds.sw_lon}&ne_lat=${bounds.ne_lat}&ne_lon=${bounds.ne_lon}`,
  ))
}

export async function lookupWeather(latitude: number, longitude: number): Promise<WeatherResult> {
  return readResponse<WeatherResult>(await fetch(
    `${weatherLookupUrl}?lat=${encodeURIComponent(latitude)}&lon=${encodeURIComponent(longitude)}`,
  ))
}

export async function lookupTides(): Promise<TidesResult> {
  return readResponse<TidesResult>(await fetch(tidesLookupUrl))
}

const aiAskUrl = `${apiBaseUrl}/api/v1/ai/ask`
const moveCarUrl = `${apiBaseUrl}/api/v1/move-car/recommend`

export async function askFloodGuard(params: {
  question: string
  latitude?: number | null
  longitude?: number | null
}, signal?: AbortSignal): Promise<AskFloodGuardResult> {
  return readResponse<AskFloodGuardResult>(await fetch(aiAskUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question: params.question,
      latitude: params.latitude ?? null,
      longitude: params.longitude ?? null,
    }),
    signal,
  }))
}

export async function getMoveMyCarRecommendation(locationId: number, signal?: AbortSignal): Promise<MoveMyCarResult> {
  return readResponse<MoveMyCarResult>(await fetch(moveCarUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...await privateHeaders() },
    body: JSON.stringify({ location_id: locationId }),
    signal,
  }))
}

export interface FamilyPlanPayload {
  meeting_place: string
  emergency_contact: string
  notes: string
  water_ready: boolean
  medication_ready: boolean
  documents_ready: boolean
  evacuation_route_ready: boolean
}

export interface FloodReport {
  id: number
  address: string
  description: string
  observed_at: string
  created_at: string
  latitude: number
  longitude: number
  verification_status: 'unverified' | 'verified' | 'rejected'
}

const familyPlanUrl = `${apiBaseUrl}/api/v1/family-plan/`
const reportsUrl = `${apiBaseUrl}/api/v1/reports/`

export async function getFamilyPlan(): Promise<FamilyPlanPayload> {
  return readResponse<FamilyPlanPayload>(await fetch(familyPlanUrl, { headers: await privateHeaders() }))
}

export async function saveFamilyPlan(plan: FamilyPlanPayload): Promise<FamilyPlanPayload> {
  return readResponse<FamilyPlanPayload>(await fetch(familyPlanUrl, {
    method: 'PUT', headers: { 'Content-Type': 'application/json', ...await privateHeaders() },
    body: JSON.stringify(plan),
  }))
}

export async function getFloodReports(): Promise<FloodReport[]> {
  return readResponse<FloodReport[]>(await fetch(reportsUrl, { headers: await privateHeaders() }))
}

export async function createFloodReport(payload: { address: string; description: string; observed_at: string }): Promise<FloodReport> {
  return readResponse<FloodReport>(await fetch(reportsUrl, {
    method: 'POST', headers: { 'Content-Type': 'application/json', ...await privateHeaders() },
    body: JSON.stringify(payload),
  }))
}

export async function deleteFloodReport(id: number): Promise<void> {
  return readResponse<void>(await fetch(`${reportsUrl}${id}`, { method: 'DELETE', headers: await privateHeaders() }))
}
