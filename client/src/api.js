export async function extractData(transcript) {
  const r = await fetch('/api/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript })
  })
  if (!r.ok) throw new Error('extract failed')
  return r.json()
}

export async function matchTrials(transcript) {
  const r = await fetch('/api/match', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transcript })
  })
  if (!r.ok) throw new Error('match failed')
  return r.json()
}
