import Phaser from 'phaser';
import { SceneKeys } from '../app/scene-keys';

export class LandingScene extends Phaser.Scene {
  constructor() {
    super(SceneKeys.Landing);
  }

  create(): void {
    const { width, height } = this.scale;

    this.cameras.main.setBackgroundColor('#05263a');

    this.add
      .text(width / 2, height * 0.34, 'WELCOME TO', {
        fontFamily: 'monospace',
        fontSize: '24px',
        color: '#fcbd22'
      })
      .setOrigin(0.5);

    this.add
      .text(width / 2, height * 0.43, 'PHU QUOC:\nPIXEL ISLAND', {
        fontFamily: 'monospace',
        fontSize: '44px',
        fontStyle: 'bold',
        align: 'center',
        color: '#ffffff'
      })
      .setOrigin(0.5);

    const enter = this.add
      .text(width / 2, height * 0.66, 'ENTER THE ISLAND', {
        fontFamily: 'monospace',
        fontSize: '22px',
        fontStyle: 'bold',
        color: '#05263a',
        backgroundColor: '#fcbd22',
        padding: { x: 24, y: 14 }
      })
      .setOrigin(0.5)
      .setInteractive({ useHandCursor: true });

    enter.on('pointerdown', () => {
      enter.setText('FOUNDATION READY');
    });
  }
}
