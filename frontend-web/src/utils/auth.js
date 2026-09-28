import { ref } from 'vue'
import { getCurrentUser } from './api'

const currentUser = ref(null)
let pending = null
let verifiedAt = 0

function notify() {
  if (typeof window !== 'undefined') window.dispatchEvent(new Event('price-agent-auth-changed'))
}

export function getAuthUser() {
  return currentUser.value
}

export function getAuthEmail() {
  return currentUser.value?.user_email || ''
}

export function isAuthenticated() {
  return Boolean(currentUser.value)
}

export function setAuthUser(user) {
  currentUser.value = user
  verifiedAt = Date.now()
  if (typeof window !== 'undefined') window.localStorage.removeItem('price-agent-auth-email')
  notify()
}

export function clearAuth() {
  currentUser.value = null
  verifiedAt = 0
  if (typeof window !== 'undefined') window.localStorage.removeItem('price-agent-auth-email')
  notify()
}

export async function refreshAuth({ force = false } = {}) {
  if (pending) return pending
  if (!force && currentUser.value && Date.now() - verifiedAt < 60_000) return currentUser.value
  pending = getCurrentUser()
    .then((user) => {
      setAuthUser(user)
      return user
    })
    .catch(() => {
      clearAuth()
      return null
    })
    .finally(() => { pending = null })
  return pending
}
