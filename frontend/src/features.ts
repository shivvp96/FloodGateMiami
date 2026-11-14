export type FeatureId =
  | 'dashboard'
  | 'property'
  | 'vehicle'
  | 'move-car'
  | 'weather'
  | 'report'
  | 'ai'
  | 'insurance'
  | 'king-tide'
  | 'family-plan'
  | 'memory'

export const features: Array<{ id: FeatureId; label: string; icon: string; description: string }> = [
  { id: 'dashboard', label: 'Dashboard', icon: '⌂', description: 'Your Miami flood-readiness overview.' },
  { id: 'property', label: 'My Property', icon: '⌂', description: 'Save the places you protect.' },
  { id: 'vehicle', label: 'My Vehicle', icon: '▣', description: 'Keep important parking locations ready.' },
  { id: 'move-car', label: 'Move My Car', icon: '⚑', description: 'Evidence-based flood-risk advisory for saved vehicles.' },
  { id: 'weather', label: 'Tide & Weather', icon: '≈', description: 'Live NWS forecast, alerts, and NOAA tide data.' },
  { id: 'report', label: 'Report Flooding', icon: '!', description: 'Keep a private log of flood observations.' },
  { id: 'ai', label: 'Ask FloodGuard AI', icon: '✦', description: 'Grounded flood-safety answers from live FEMA, NWS, and NOAA data.' },
  { id: 'insurance', label: 'Flood Insurance', icon: '◒', description: 'NFIP and FEMA resources plus address-specific zone context.' },
  { id: 'king-tide', label: 'King Tide Watch', icon: '◔', description: 'Elevated predicted tides at Virginia Key (NOAA CO-OPS).' },
  { id: 'family-plan', label: 'Family Flood Plan', icon: '♡', description: 'Save your household evacuation plan and readiness checklist.' },
  { id: 'memory', label: 'Flood Memory', icon: '◉', description: 'Review your private historical flood incidents.' },
]
