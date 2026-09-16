export const SceneKeys = {
  Boot: 'BootScene',
  Landing: 'LandingScene',
  Airport: 'AirportScene',
  Character: 'CharacterScene',
  IslandMap: 'IslandMapScene',
  NoBrakes: 'NoBrakesScene',
  Result: 'ResultScene'
} as const;

export type SceneKey = (typeof SceneKeys)[keyof typeof SceneKeys];
