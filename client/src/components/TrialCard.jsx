import React from 'react'

function line(list) {
  if (!list || !list.length) return '—'
  return list.join(', ')
}

export default function TrialCard({ study }) {
  const id = (study.NCTId || [])[0]
  const title = (study.BriefTitle || [])[0]
  const status = (study.OverallStatus || [])[0]
  const badgeClass = status ? status.toLowerCase().replace(/[^a-z0-9]+/g, '_') : ''
  const cond = line(study.Condition)
  const gender = (study.Gender || [])[0] || 'All'
  const minAge = (study.MinimumAge || [])[0] || 'N/A'
  const maxAge = (study.MaximumAge || [])[0] || 'N/A'
  const city = line(study.LocationCity)
  const state = line(study.LocationState)
  const country = line(study.LocationCountry)
  const phase = line(study.Phase)
  const studyType = line(study.StudyType)
  const interventions = line(study.InterventionName)
  const summary = ((study.BriefSummary || [])[0] || '').slice(0, 280)

  const url = id ? `https://clinicaltrials.gov/study/${id}` : undefined

  return (
    <article className="card">
      <header>
        <h3>{title || 'Untitled Trial'}</h3>
        {status && <span className={`badge ${badgeClass}`}>{status}</span>}
      </header>
      <p className="muted">{summary}{summary.length === 280 ? '…' : ''}</p>
      <div className="meta">
        <div><strong>NCT</strong>: {id}</div>
        <div><strong>Condition</strong>: {cond}</div>
        <div><strong>Phase</strong>: {phase}</div>
        <div><strong>Type</strong>: {studyType}</div>
        <div><strong>Interventions</strong>: {interventions}</div>
        <div><strong>Gender</strong>: {gender}</div>
        <div><strong>Age</strong>: {minAge} - {maxAge}</div>
        <div><strong>Locations</strong>: {city} {state ? `(${state})` : ''} {country}</div>
      </div>
      {url && <a className="link" href={url} target="_blank" rel="noreferrer">View on ClinicalTrials.gov →</a>}
    </article>
  )
}
