import { supabase } from './supabase'

const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

export async function apiFetch(path, options = {}) {
  const { data: { session } } = await supabase.auth.getSession()
  const headers = new Headers(options.headers || {})
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  // FormData must set its own Content-Type: the browser appends the multipart
  // boundary, and overriding it with application/json makes the server unable
  // to parse the body at all.
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
  if (options.body && !isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`${API_URL}${path}`, { ...options, headers })
  if (response.status === 401) {
    await supabase.auth.signOut()
    throw new Error('Your session expired. Please sign in again.')
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `Request failed (${response.status})`)
  }
  return response
}
