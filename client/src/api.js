const BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

export async function extractData(transcript) {
  const r = await fetch(`${BASE}/api/extract`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript })
  })
  if (!r.ok) throw new Error('extract failed')
  return r.json()
}

export async function matchTrials(transcript) {
  const r = await fetch(`${BASE}/api/match`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript })
  })
  if (!r.ok) throw new Error('match failed')
  return r.json()
}
