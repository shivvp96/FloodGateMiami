/** Minimal Supabase email authentication client; only publishable browser credentials belong here. */
export interface SessionUser { id: string; email?: string }
interface Session { access_token: string; refresh_token: string; expires_at: number; user: SessionUser }
const storageKey = 'floodguard-supabase-session'
const url = (import.meta.env.VITE_SUPABASE_URL ?? '').replace(/\/$/, '')
const publicKey = import.meta.env.VITE_SUPABASE_ANON_KEY ?? ''
let refreshRequest: Promise<Session | null> | null = null

export const authConfigured = Boolean(url && publicKey)

function parseSession(raw: unknown): Session | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Partial<Session>
  if (typeof obj.access_token !== 'string' || typeof obj.refresh_token !== 'string'
      || typeof obj.expires_at !== 'number' || typeof obj.user?.id !== 'string') return null
  return obj as Session
}

function stored(): Session | null {
  try { return parseSession(JSON.parse(localStorage.getItem(storageKey) ?? 'null')) }
  catch { return null }
}

function notify() { window.dispatchEvent(new Event('floodguard-auth-changed')) }
function store(session: Session | null) {
  if (session) localStorage.setItem(storageKey, JSON.stringify(session))
  else localStorage.removeItem(storageKey)
  notify()
}

export function currentUser(): SessionUser | null { return stored()?.user ?? null }
export function subscribeAuth(listener: () => void): () => void {
  window.addEventListener('floodguard-auth-changed', listener)
  window.addEventListener('storage', listener)
  return () => {
    window.removeEventListener('floodguard-auth-changed', listener)
    window.removeEventListener('storage', listener)
  }
}

async function request(path: string, payload: unknown, token?: string): Promise<Record<string, unknown>> {
  if (!authConfigured) throw new Error('Supabase Auth is not configured. Contact the site administrator.')
  const response = await fetch(`${url}/auth/v1${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      apikey: publicKey,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
  })
  const body = await response.json().catch(() => ({})) as Record<string, unknown>
  if (!response.ok) throw new Error(String(body.msg ?? body.error_description ?? body.message ?? body.error ?? 'Authentication failed'))
  return body
}

function asSession(body: Record<string, unknown>): Session | null {
  if (typeof body.access_token !== 'string' || typeof body.refresh_token !== 'string') return null
  const user = body.user as SessionUser | undefined
  if (!user || typeof user.id !== 'string') return null
  const expiresIn = typeof body.expires_in === 'number' ? body.expires_in : 3600
  return {
    access_token: body.access_token,
    refresh_token: body.refresh_token,
    expires_at: Math.floor(Date.now() / 1000) + expiresIn,
    user: { id: user.id, email: user.email },
  }
}

export async function signIn(email: string, password: string): Promise<void> {
  const body = await request('/token?grant_type=password', { email, password })
  const session = asSession(body)
  if (!session) throw new Error('Sign-in did not return a session')
  store(session)
}

export async function signUp(email: string, password: string): Promise<boolean> {
  const body = await request('/signup', { email, password })
  const session = asSession(body)
  if (session) store(session)
  return Boolean(session)
}

export async function signOut(): Promise<void> {
  const session = stored()
  store(null) // sign out locally even if the network is down
  if (session) {
    try { await request('/logout', {}, session.access_token) } catch { /* session already cleared */ }
  }
}

async function refresh(): Promise<Session | null> {
  const session = stored()
  if (!session || !authConfigured) return null
  try {
    const result = await request('/token?grant_type=refresh_token', { refresh_token: session.refresh_token })
    const newSession = asSession(result)
    store(newSession)
    return newSession
  } catch {
    store(null)
    return null
  }
}

export async function getAccessToken(): Promise<string | null> {
  const session = stored()
  if (!session) return null
  if (session.expires_at > Math.floor(Date.now() / 1000) + 60) return session.access_token
  if (!refreshRequest) refreshRequest = refresh().finally(() => { refreshRequest = null })
  return (await refreshRequest)?.access_token ?? null
}

export async function privateHeaders(): Promise<Record<string, string>> {
  const token = await getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}
