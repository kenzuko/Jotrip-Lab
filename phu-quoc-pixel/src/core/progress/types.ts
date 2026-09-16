export const CHARACTER_IDS = [
  'traveler',
  'explorer',
  'uncle',
  'grandma',
  'kid',
  'fisherman',
  'ridgeback',
  'pepper'
] as const;

export type CharacterId = (typeof CHARACTER_IDS)[number];

export interface PlayerProfile {
  displayName: string;
  characterId: CharacterId;
}

export interface PlayerProgress {
  totalJo: number;
  mapPieces: string[];
  achievements: string[];
  bestScores: Record<string, number>;
}

export interface PlayerSettings {
  muted: boolean;
  musicVolume: number;
  sfxVolume: number;
}
