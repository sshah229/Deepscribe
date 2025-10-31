import React, { useState } from 'react'
import { extractData, matchTrials } from './api'
import TrialCard from './components/TrialCard'
import sampleTranscript from './sampleTranscript.txt?raw'

export default function App() {
  const [transcript, setTranscript] = useState('')
  const [loading, setLoading] = useState(false)
  const [extracted, setExtracted] = useState(null)
  const [results, setResults] = useState(null)
  const [error, setError] = useState('')

  const useSample = () => setTranscript(sampleTranscript)

  const onExtract = async () => {
    setError(''); setLoading(true)
    try {
      const data = await extractData(transcript)
      setExtracted(data.extracted)
    } catch (e) {
      setError('Failed to extract data')
    } finally { setLoading(false) }
  }

  const onMatch = async () => {
    setError(''); setLoading(true)
    try {
      const data = await matchTrials(transcript)
      setExtracted(data.extracted)
      setResults(data.results)
    } catch (e) {
      setError('Failed to fetch matches')
    } finally { setLoading(false) }
  }

  return (
    <div className="container">
      <header>
        <h1>DeepScribe Clinical Trials Finder</h1>
        <p>Paste a patient–doctor transcript. Extract key data, then find top trial matches.</p>
      </header>

      <section className="input-section">
        <div className="controls">
          <button onClick={useSample}>Use sample transcript</button>
          <button onClick={onExtract} disabled={!transcript || loading}>Extract data</button>
          <button className="primary" onClick={onMatch} disabled={!transcript || loading}>Find trials</button>
        </div>
        <textarea
          placeholder="Paste transcript here..."
          value={transcript}
          onChange={(e) => setTranscript(e.target.value)}
          rows={14}
        />
        {error && <div className="error">{error}</div>}
      </section>

      {extracted && (
        <section>
          <h2>Extracted Patient Data</h2>
          <div className="grid extracted">
            <div><strong>Age:</strong> {extracted.age ?? 'Unknown'}</div>
            <div><strong>Sex:</strong> {extracted.sex ?? 'Unknown'}</div>
            <div><strong>Diagnosis:</strong> {extracted.diagnosis ?? 'Unknown'}</div>
            <div>
              <strong>Keywords:</strong>
              <div className="chips">
                {(extracted.keywords || []).length ? (extracted.keywords || []).map((k, i) => (
                  <span key={i} className="chip">{k}</span>
                )) : <span className="muted">—</span>}
              </div>
            </div>
            <div>
              <strong>Locations:</strong>
              <div className="chips">
                {(extracted.locations || []).length ? (extracted.locations || []).map((k, i) => (
                  <span key={i} className="chip">{k}</span>
                )) : <span className="muted">—</span>}
              </div>
            </div>
          </div>
        </section>
      )}

      {results && (
        <section>
          <h2>Top Matching Trials ({results.count})</h2>
          <p><strong>Query:</strong> {results.expr}</p>
          <div className="grid">
            {(results.studies || []).map((s, idx) => (
              <TrialCard key={idx} study={s} />
            ))}
          </div>
        </section>
      )}

      {loading && (
        <div className="loading">
          <div className="spinner" />
        </div>
      )}

      <footer>
        <small>Backend: Flask + Gemini (optional). Data: ClinicalTrials.gov.</small>
      </footer>
    </div>
  )
}
