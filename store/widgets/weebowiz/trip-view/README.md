# Trip View

Five animated pixel worlds for your home screen: neon ramen, a kaiju film set, nebulae, a glowing forest and code rain. Explore five palettes per scene, change the animation speed, and freeze a favorite moment as wallpaper.

Open the full-screen controls to create a new animation. Pick **Codex** or **Claude**, describe a place, weather, mood or imaginary world, and tap **Agent · New animation**. Your selection is saved. Each button shows whether that CLI is installed and signed in, and which model it will use; if it isn't ready, the panel shows the terminal command to fix it. Generation uses your existing agent account and can take a few minutes. Built-in scenes work without either agent. To change a generated scene, tap **Manage this scene** under its name and choose **Edit scene** (your agent changes only what you describe; the old version is kept) or **Delete scene** (asks to confirm).

The store edition ships with **English only**. For Traditional Chinese or any other language, open **Language → Custom**, enter the language, and copy the generated prompt to your coding agent. It creates a language pack from the English template; the new language then appears in the selector.

## First use

1. Install the declared packages through the launcher.
2. Tap **Set up**. This writes the embedded, reviewed Python programs and five scenes locally, generates sounds, and validates the shaders. Setup does not download or run external scripts.
3. Tap the tile to open the controls. The optional pixel clock and sound start off; the pixel pet starts on.

To save battery, the home tile shows a still of the scene and animates for a few seconds when you tap it. Settings can switch it to always animated. The still for each scene is taken in the background the first time you switch to it.

Scene card thumbnails are rendered in the background right after setup. New agent animations get one automatically.

## Local files and updates

- Programs, scenes, English strings and MIT license: `~/.local/share/pixbg/`.
- Commands: `~/.local/bin/pixbg` and `~/.local/bin/tripview`.
- Agent selection and optional model override: `~/.config/pixbg/config.json`.
- Generated data, sounds, thumbnails and setup log: `~/.cache/pixbg/`.
- Saved wallpapers: `~/Pictures/pixbg/`. Applying wallpaper updates the launcher's background setting and theme wallpaper files.

**Update** preserves generated scenes, added language packs, language choice and agent settings. Replaced program files are backed up under `~/.cache/pixbg/install-backups/`. Setup refuses to write through a linked installation directory; update a developer checkout from its source instead. Installation does not create a second widget.

The widget invokes only the selected agent when you request generation. Your prompt and shader instructions are sent to that agent. Every generated scene is checked for syntax, AGSL restrictions and GPU cost before it is displayed. Deleting an animation removes only the selected generated scene; built-in scenes cannot be deleted from the controls.

Source: [Trip View](https://github.com/WeeboWIZ/Omalauncher_Tools/tree/trip-view/trip-view). MIT License. Copyright © 2026 WeeboWIZ.
