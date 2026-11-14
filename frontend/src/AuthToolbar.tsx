import { useEffect, useState, type FormEvent } from 'react'
import { authConfigured, currentUser, signIn, signOut, signUp, subscribeAuth } from './auth'

export default function AuthToolbar() {
  const [user, setUser] = useState(currentUser)
  const [open, setOpen] = useState(false)
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [working, setWorking] = useState(false)
  const [message, setMessage] = useState('')

  useEffect(() => subscribeAuth(() => setUser(currentUser())), [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setWorking(true)
    setMessage('')
    try {
      if (mode === 'signin') {
        await signIn(email.trim(), password)
        setOpen(false)
        setPassword('')
      } else {
        const signedIn = await signUp(email.trim(), password)
        if (signedIn) {
          setOpen(false)
          setPassword('')
        } else {
          setMessage('Account created. Check your email to confirm your account, then sign in.')
        }
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Authentication failed.')
    } finally { setWorking(false) }
  }

  return (
    <div className="fixed right-3 top-3 z-[3000] text-sm sm:right-5">
      {user ? (
        <div className="flex items-center gap-2 rounded-xl border border-slate-600 bg-ink-950/95 p-2 shadow-xl">
          <span className="max-w-32 truncate text-slate-200 sm:max-w-48" title={user.email}>{user.email ?? 'Signed in'}</span>
          <button className="rounded-lg border border-slate-600 px-3 py-1.5 text-white hover:bg-slate-700" onClick={() => { void signOut() }}>Sign out</button>
        </div>
      ) : (
        <button className="rounded-xl border border-ocean-300 bg-ink-950 px-4 py-2 font-semibold text-ocean-300 shadow-xl hover:bg-ink-800" onClick={() => { setOpen(true); setMessage('') }}>
          Sign in / Sign up
        </button>
      )}
      {open && (
        <div className="fixed inset-0 z-[3001] flex items-center justify-center bg-black/75 p-4" role="presentation" onMouseDown={e => { if (e.target === e.currentTarget) setOpen(false) }}>
          <section role="dialog" aria-modal="true" aria-labelledby="auth-title" className="w-full max-w-md rounded-2xl border border-slate-600 bg-ink-900 p-6 text-white shadow-2xl">
            <div className="flex items-center justify-between">
              <h2 id="auth-title" className="text-xl font-bold">{mode === 'signin' ? 'Sign in to FloodGuard' : 'Create your account'}</h2>
              <button type="button" aria-label="Close" className="rounded-lg px-2 py-1 text-slate-300 hover:bg-slate-700" onClick={() => setOpen(false)}>✕</button>
            </div>
            <p className="mt-2 text-slate-300">Your saved properties and vehicles remain private to your account.</p>
            {!authConfigured && <p role="alert" className="mt-3 rounded-lg border border-amber-400/50 bg-amber-400/10 p-3 text-amber-200">Sign-in is not configured yet. Add the Supabase public project settings to the frontend deployment.</p>}
            <form onSubmit={e => { void submit(e) }} className="mt-5 space-y-4">
              <label className="block text-sm text-slate-200">Email
                <input autoComplete="email" type="email" required value={email} onChange={e => setEmail(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-600 bg-ink-950 p-3 text-white" />
              </label>
              <label className="block text-sm text-slate-200">Password
                <input autoComplete={mode === 'signup' ? 'new-password' : 'current-password'} type="password" minLength={6} required value={password} onChange={e => setPassword(e.target.value)} className="mt-1 w-full rounded-lg border border-slate-600 bg-ink-950 p-3 text-white" />
              </label>
              {message && <p role="alert" className="rounded-lg border border-slate-500 bg-ink-950 p-3 text-sm text-slate-200">{message}</p>}
              <button disabled={!authConfigured || working} className="w-full rounded-lg bg-ocean-400 p-3 font-semibold text-ink-950 disabled:opacity-50">{working ? 'Working…' : mode === 'signin' ? 'Sign in' : 'Create account'}</button>
            </form>
            <button type="button" className="mt-4 text-sm text-ocean-300 hover:underline" onClick={() => { setMode(mode === 'signin' ? 'signup' : 'signin'); setMessage('') }}>
              {mode === 'signin' ? 'Need an account? Sign up' : 'Already have an account? Sign in'}
            </button>
          </section>
        </div>
      )}
    </div>
  )
}
