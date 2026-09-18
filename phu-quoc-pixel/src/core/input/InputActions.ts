import Phaser from 'phaser';

export type InputCleanup = () => void;

export class InputActions {
  bindPrimary(scene: Phaser.Scene, callback: () => void): InputCleanup {
    const pointerHandler = (): void => callback();
    const keyboardHandler = (): void => callback();

    scene.input.on('pointerdown', pointerHandler);
    scene.input.keyboard?.on('keydown-SPACE', keyboardHandler);

    let active = true;
    const cleanup = (): void => {
      if (!active) return;
      active = false;
      scene.input.off('pointerdown', pointerHandler);
      scene.input.keyboard?.off('keydown-SPACE', keyboardHandler);
      scene.events.off(Phaser.Scenes.Events.SHUTDOWN, cleanup);
    };

    scene.events.once(Phaser.Scenes.Events.SHUTDOWN, cleanup);
    return cleanup;
  }

  bindBack(scene: Phaser.Scene, callback: () => void): InputCleanup {
    const keyboardHandler = (): void => callback();
    scene.input.keyboard?.on('keydown-ESC', keyboardHandler);

    let active = true;
    const cleanup = (): void => {
      if (!active) return;
      active = false;
      scene.input.keyboard?.off('keydown-ESC', keyboardHandler);
      scene.events.off(Phaser.Scenes.Events.SHUTDOWN, cleanup);
    };

    scene.events.once(Phaser.Scenes.Events.SHUTDOWN, cleanup);
    return cleanup;
  }
}

export const inputActions = new InputActions();
