import Phaser from 'phaser';

interface ButtonOptions {
  width?: number;
  backgroundColor?: string;
  color?: string;
  fontSize?: number;
}

export function createButton(
  scene: Phaser.Scene,
  x: number,
  y: number,
  label: string,
  onPress: () => void,
  options: ButtonOptions = {}
): Phaser.GameObjects.Text {
  const button = scene.add
    .text(x, y, label, {
      fontFamily: 'monospace',
      fontSize: `${options.fontSize ?? 20}px`,
      fontStyle: 'bold',
      align: 'center',
      fixedWidth: options.width ?? 300,
      color: options.color ?? '#05263a',
      backgroundColor: options.backgroundColor ?? '#fcbd22',
      padding: { x: 16, y: 13 }
    })
    .setOrigin(0.5)
    .setInteractive({ useHandCursor: true });

  button.on('pointerdown', onPress);
  return button;
}
