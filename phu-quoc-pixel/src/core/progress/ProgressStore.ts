import { CHARACTER_IDS, type CharacterId, type PlayerProfile, type PlayerProgress, type PlayerSettings } from './types';

const KEYS = {
  profile: 'pqpi:v1:profile',
  progress: 'pqpi:v1:progress',
  settings: 'pqpi:v1:settings'
} as const;

const DEFAULT_PROFILE: PlayerProfile = {
  displayName: 'Traveler',
  characterId: 'traveler'
};

const DEFAULT_PROGRESS: PlayerProgress = {
  totalJo: 0,
  mapPieces: [],
  achievements: [],
  bestScores: {}
};

const DEFAULT_SETTINGS: PlayerSettings = {
  muted: false,
  musicVolume: 0.7,
  sfxVolume: 0.8
};

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return structuredClone(fallback);
    return { ...structuredClone(fallback), ...JSON.parse(raw) } as T;
  } catch {
    return structuredClone(fallback);
  }
}

function writeJson(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage can be unavailable in private or restricted browser contexts.
  }
}

export class ProgressStore {
  private profile: PlayerProfile = readJson(KEYS.profile, DEFAULT_PROFILE);
  private progress: PlayerProgress = readJson(KEYS.progress, DEFAULT_PROGRESS);
  private settings: PlayerSettings = readJson(KEYS.settings, DEFAULT_SETTINGS);

  constructor() {
    if (!CHARACTER_IDS.includes(this.profile.characterId)) {
      this.profile.characterId = DEFAULT_PROFILE.characterId;
    }
  }

  getProfile(): PlayerProfile {
    return structuredClone(this.profile);
  }

  getProgress(): PlayerProgress {
    return structuredClone(this.progress);
  }

  getSettings(): PlayerSettings {
    return structuredClone(this.settings);
  }

  setDisplayName(displayName: string): void {
    const cleaned = displayName.trim().slice(0, 18) || DEFAULT_PROFILE.displayName;
    this.profile = { ...this.profile, displayName: cleaned };
    writeJson(KEYS.profile, this.profile);
  }

  setCharacter(characterId: CharacterId): void {
    this.profile = { ...this.profile, characterId };
    writeJson(KEYS.profile, this.profile);
  }

  addJo(amount: number): number {
    const safeAmount = Math.max(0, Math.floor(amount));
    this.progress = { ...this.progress, totalJo: this.progress.totalJo + safeAmount };
    writeJson(KEYS.progress, this.progress);
    return this.progress.totalJo;
  }

  setBestScore(gameId: string, score: number): number {
    const safeScore = Math.max(0, Math.floor(score));
    const current = this.progress.bestScores[gameId] ?? 0;
    const best = Math.max(current, safeScore);
    this.progress = {
      ...this.progress,
      bestScores: { ...this.progress.bestScores, [gameId]: best }
    };
    writeJson(KEYS.progress, this.progress);
    return best;
  }

  updateSettings(next: Partial<PlayerSettings>): void {
    this.settings = {
      ...this.settings,
      ...next,
      musicVolume: Math.max(0, Math.min(1, next.musicVolume ?? this.settings.musicVolume)),
      sfxVolume: Math.max(0, Math.min(1, next.sfxVolume ?? this.settings.sfxVolume))
    };
    writeJson(KEYS.settings, this.settings);
  }
}

export const progressStore = new ProgressStore();
