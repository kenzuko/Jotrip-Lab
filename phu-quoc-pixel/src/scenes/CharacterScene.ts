import Phaser from 'phaser';
import { SceneKeys } from '../app/scene-keys';
import { flowController } from '../core/navigation/FlowController';
import { progressStore } from '../core/progress/ProgressStore';
import type { CharacterId } from '../core/progress/types';
import { createButton } from '../ui/createButton';

const CHARACTERS: readonly { id: CharacterId; label: string }[] = [
  { id: 'traveler', label: 'TRAVELER' },
  { id: 'explorer', label: 'EXPLORER' },
  { id: 'uncle', label: 'UNCLE' },
  { id: 'grandma', label: 'GRANDMA' },
  { id: 'kid', label: 'KID' },
  { id: 'fisherman', label: 'OLD FISHERMAN' },
  { id: 'ridgeback', label: 'RIDGEBACK' },
  { id: 'pepper', label: 'PEPPER' }
];

export class CharacterScene extends Phaser.Scene {
  constructor() {
    super(SceneKeys.Character);
  }

  create(): void {
    const { width } = this.scale;
    this.cameras.main.setBackgroundColor('#0b3145');

    this.add
      .text(width / 2, 80, 'WHO ARE YOU TODAY?', {
        fontFamily: 'monospace',
        fontSize: '31px',
        fontStyle: 'bold',
        color: '#ffffff'
      })
      .setOrigin(0.5);

    const selectedText = this.add
      .text(width / 2, 135, `SELECTED: ${progressStore.getProfile().characterId.toUpperCase()}`, {
        fontFamily: 'monospace',
        fontSize: '14px',
        color: '#fcbd22'
      })
      .setOrigin(0.5);

    CHARACTERS.forEach((character, index) => {
      const col = index % 2;
      const row = Math.floor(index / 2);
      const x = col === 0 ? 155 : 385;
      const y = 235 + row * 115;
      createButton(
        this,
        x,
        y,
        character.label,
        () => {
          progressStore.setCharacter(character.id);
          selectedText.setText(`SELECTED: ${character.label}`);
        },
        {
          width: 190,
          fontSize: character.label.length > 11 ? 13 : 16,
          backgroundColor: '#164b61',
          color: '#ffffff'
        }
      );
    });

    createButton(this, width / 2, 790, 'OPEN THE MAP', () => {
      flowController.go(this, SceneKeys.IslandMap);
    });
  }
}
