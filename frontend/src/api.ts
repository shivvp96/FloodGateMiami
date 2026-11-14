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

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const baseUrl = `${apiBaseUrl}/api/v1/saved-locations/`
const addressLookupUrl = `${apiBaseUrl}/api/v1/address/lookup`
const addressOverlayUrl = `${apiBaseUrl}/api/v1/address/overlay`
const weatherLookupUrl = `${apiBaseUrl}/api/v1/weather/lookup`
const tidesLookupUrl = `${apiBaseUrl}/api/v1/tides/lookup`

async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(payload?.detail || `Request failed (${response.status})`)
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>
}

export async function getSavedLocations(ownerType: OwnerType): Promise<SavedLocation[]> {
  return readResponse<SavedLocation[]>(await fetch(`${baseUrl}?owner_type=${ownerType}`))
}

export async function createSavedLocation(location: Omit<SavedLocation, 'id' | 'created_at'>): Promise<SavedLocation> {
  return readResponse<SavedLocation>(await fetch(baseUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(location),
  }))
}

export async function deleteSavedLocation(id: number): Promise<void> {
  return readResponse<void>(await fetch(`${baseUrl}${id}`, { method: 'DELETE' }))
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
