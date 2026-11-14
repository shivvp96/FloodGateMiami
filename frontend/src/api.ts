export type OwnerType = 'property' | 'vehicle'

export interface SavedLocation {
  id: number
  owner_type: OwnerType
  label: string
  address: string
  created_at: string
}

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const baseUrl = `${apiBaseUrl}/api/v1/saved-locations/`

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
