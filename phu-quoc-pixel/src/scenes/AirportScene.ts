import Phaser from 'phaser';
import { SceneKeys } from '../app/scene-keys';
import { flowController } from '../core/navigation/FlowController';
import { createButton } from '../ui/createButton';

export class AirportScene extends Phaser.Scene {
  constructor() {
    super(SceneKeys.Airport);
  }

  create(): void {
    const { width, height } = this.scale;
    this.cameras.main.setBackgroundColor('#1a5871');

    this.add
      .text(width / 2, 150, 'PHU QUOC INTERNATIONAL AIRPORT', {
        fontFamily: 'monospace',
        fontSize: '16px',
        color: '#fcbd22'
      })
      .setOrigin(0.5);

    this.add
      .text(width / 2, 250, 'YOU MADE IT.', {
        fontFamily: 'monospace',
        fontSize: '42px',
        fontStyle: 'bold',
        color: '#ffffff'
      })
      .setOrigin(0.5);

    this.add.rectangle(width / 2, 500, 410, 230, 0x062c3d, 0.92);
    this.add
      .text(92, 420, 'KEN · LOCAL GUIDE', {
        fontFamily: 'monospace',
        fontSize: '14px',
        color: '#fcbd22'
      });
    this.add
      .text(92, 465, 'Welcome to Phu Quoc.\nWhere would you like to go?', {
        fontFamily: 'monospace',
        fontSize: '20px',
        color: '#ffffff',
        lineSpacing: 8
      });

    createButton(this, width / 2, 670, "LET'S GO", () => {
      flowController.go(this, SceneKeys.Character);
    });
  }
}
