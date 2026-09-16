import Phaser from 'phaser';
import { BootScene } from '../scenes/BootScene';
import { LandingScene } from '../scenes/LandingScene';

export const GAME_WIDTH = 540;
export const GAME_HEIGHT = 960;

export const gameConfig: Phaser.Types.Core.GameConfig = {
  type: Phaser.AUTO,
  parent: 'game-shell',
  width: GAME_WIDTH,
  height: GAME_HEIGHT,
  backgroundColor: '#05263a',
  pixelArt: true,
  scale: {
    mode: Phaser.Scale.FIT,
    autoCenter: Phaser.Scale.CENTER_BOTH,
    width: GAME_WIDTH,
    height: GAME_HEIGHT
  },
  scene: [BootScene, LandingScene]
};
