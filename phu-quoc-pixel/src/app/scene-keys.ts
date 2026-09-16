export const SceneKeys = {
  Boot: 'BootScene',
  Landing: 'LandingScene'
} as const;

export type SceneKey = (typeof SceneKeys)[keyof typeof SceneKeys];
