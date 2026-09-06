"use client";

import { useInstrument } from "@/contexts/InstrumentContext";

export default function InstrumentSelector() {
  const { instrument, setInstrument, instruments } = useInstrument();

  return (
    <div className="inst-selector">
      <label className="inst-label" htmlFor="instrument-select">
        Instrument
      </label>
      <select
        id="instrument-select"
        className="inst-select"
        value={instrument}
        onChange={(e) => setInstrument(e.target.value as typeof instrument)}
      >
        {instruments.map((inst) => (
          <option key={inst} value={inst}>
            {inst}
          </option>
        ))}
      </select>

      <style jsx>{`
        .inst-selector {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .inst-label {
          font-size: 0.75rem;
          color: var(--color-text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .inst-select {
          background: var(--color-surface);
          border: 1px solid var(--color-border);
          border-radius: 6px;
          padding: 0.35rem 0.6rem;
          font-size: 0.8rem;
          font-family: var(--font-mono);
          color: var(--color-text);
          cursor: pointer;
          outline: none;
        }
        .inst-select:focus {
          border-color: var(--color-accent);
        }
      `}</style>
    </div>
  );
}
