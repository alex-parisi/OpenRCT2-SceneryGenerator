# OpenRCT2 Scenery Generator Tutorial
## Animated Small Scenery (Basic)

### 1. Start with the dumpster example

It's recommended to follow [this guide](small-scenery-advanced-tutorial.md) to set up the dumpster example. We'll be animating the lid to demonstrate basic keyframe animations.


<img src="_static/blender-dumpster-scene.png" width="1840" alt="">


### 2. Open the Animation Editor

In the top bar, click `Animation`:


<img src="_static/blender-animator.png" width="1840" alt="">


Then in the `Outliner` panel in the top-right, expand the nodes until you can select `Cap_02`.

### 3. Keyframe Base Orientation

For each object that is going to be moving in the scene, we need to keyframe the beginning, intermediate, and ending positions.

While `Cap_02` is still selected, open the `Object Properties` panel, and in the `Transform` section click the small dot next to `Rotation W` and `Rotation X` to set the initial keyframes:


<img src="_static/blender-keyframe-1.png" width="250" alt="">


You should see the keyframes appear in the Animation editor at the bottom:


<img src="_static/blender-keyframe-2.png" width="300" alt="">


### 4. Set Next Orientation & Keyframes

Since OpenRCT2 expects animations to be in powers of 2 (i.e. 8, 16, 32), we'll move the scrubber to frame 32:


<img src="_static/blender-keyframe-3.png" width="300" alt="">


Then, back in the `Transform` section, we'll set `Rotation W = 0.609` and `Rotation X = 0.793`, then click the diamonds to set the next keyframe:


<img src="_static/blender-keyframe-4.png" width="300" alt="">


And like before, you should now see these keyframes in the Animation editor:


<img src="_static/blender-keyframe-5.png" width="300" alt="">


If you move the scrubber between frames 1 and 32, you should see the lid open and close!


<img src="_static/blender-animation-preview.gif" width="480" alt="">


### 5. Configure Add-On

Back in the `Layout` editor, open the plugin by pressing `N`.

You now want to click the `Animated` button, which will turn blue and expose a new area:


<img src="_static/blender-animation-settings.png" width="300" alt="">


We'll use the following settings:

- `Cycle`: 32 frames
- `Playback`: Ping-Pong - this will have the lid close and then open again, returning back to the original position.
- `Speed`: 1
- `Deformation`: Rigid only - this is because the transformations we are animating do not deform any of the object meshes.
- `Start Frame`: 1
- `End Frame`: 32

### 6. Export and Test In-Game

Press the `Export .parkobj` button, save the file and add it to your objects folder. Then select and build it in-game:


<img src="_static/dumpster-in-game-animated.gif" width="315" alt="">