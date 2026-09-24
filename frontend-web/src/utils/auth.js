const AUTH_EMAIL_KEY = 'price-agent-auth-email'

export function getAuthEmail() {
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(AUTH_EMAIL_KEY) || ''
}

export function isAuthenticated() {
  return Boolean(getAuthEmail())
}

export function setAuthEmail(email) {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(AUTH_EMAIL_KEY, email)
    window.dispatchEvent(new Event('price-agent-auth-changed'))
  }
}

export function clearAuth() {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(AUTH_EMAIL_KEY)
    window.dispatchEvent(new Event('price-agent-auth-changed'))
  }
}
