"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

const SUPPORTED_INSTRUMENTS = [
  "XAU/USD",
  "EUR/USD",
  "GBP/USD",
  "USD/JPY",
  "BTC/USD",
  "ETH/USD",
  "US30",
] as const;

type Instrument = (typeof SUPPORTED_INSTRUMENTS)[number];

interface InstrumentContextValue {
  instrument: Instrument;
  setInstrument: (inst: Instrument) => void;
  instruments: readonly Instrument[];
}

const InstrumentContext = createContext<InstrumentContextValue | null>(null);

export function InstrumentProvider({ children }: { children: ReactNode }) {
  const [instrument, setInstrumentState] = useState<Instrument>("XAU/USD");

  const setInstrument = useCallback((inst: Instrument) => {
    setInstrumentState(inst);
  }, []);

  return (
    <InstrumentContext.Provider
      value={{ instrument, setInstrument, instruments: SUPPORTED_INSTRUMENTS }}
    >
      {children}
    </InstrumentContext.Provider>
  );
}

export function useInstrument(): InstrumentContextValue {
  const ctx = useContext(InstrumentContext);
  if (!ctx) {
    // Fallback for components used outside provider (shouldn't happen)
    return {
      instrument: "XAU/USD",
      setInstrument: () => {},
      instruments: SUPPORTED_INSTRUMENTS,
    };
  }
  return ctx;
}

export type { Instrument };
export { SUPPORTED_INSTRUMENTS };
