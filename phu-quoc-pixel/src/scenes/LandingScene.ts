import Phaser from 'phaser';
import { SceneKeys } from '../app/scene-keys';
import { flowController } from '../core/navigation/FlowController';
import { createButton } from '../ui/createButton';

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

    this.add
      .text(width / 2, height * 0.56, 'EXPLORE · DISCOVER · PLAY', {
        fontFamily: 'monospace',
        fontSize: '14px',
        color: '#9ec9d9'
      })
      .setOrigin(0.5);

    createButton(this, width / 2, height * 0.69, 'ENTER THE ISLAND', () => {
      flowController.go(this, SceneKeys.Airport);
    });
  }
}
