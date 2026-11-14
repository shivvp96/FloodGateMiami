export type FeatureId =
  | 'dashboard'
  | 'property'
  | 'vehicle'
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
  { id: 'weather', label: 'Tide & Weather', icon: '≈', description: 'Live NWS forecast, alerts, and NOAA tide data.' },
  { id: 'report', label: 'Report Flooding', icon: '!', description: 'Photo and incident reports arrive in a later phase.' },
  { id: 'ai', label: 'Ask FloodGuard AI', icon: '✦', description: 'Personalized AI guidance arrives in Phase 3.' },
  { id: 'insurance', label: 'Flood Insurance', icon: '◒', description: 'Insurance guidance arrives in Phase 5.' },
  { id: 'king-tide', label: 'King Tide Watch', icon: '◔', description: 'Elevated predicted tides at Virginia Key (NOAA CO-OPS).' },
  { id: 'family-plan', label: 'Family Flood Plan', icon: '♡', description: 'Build a preparedness plan in Phase 5.' },
  { id: 'memory', label: 'Flood Memory', icon: '◉', description: 'Capture flood memories in Phase 5.' },
]
