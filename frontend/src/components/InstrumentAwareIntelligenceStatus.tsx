"use client";

import { useInstrument } from "@/contexts/InstrumentContext";
import IntelligenceStatus from "./IntelligenceStatus";

export default function InstrumentAwareIntelligenceStatus() {
  const { instrument } = useInstrument();
  return <IntelligenceStatus instrument={instrument} strategyId="default" />;
}
