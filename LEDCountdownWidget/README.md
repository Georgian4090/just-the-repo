# LED Countdown Widget

A home-screen countdown widget styled after LED display clocks: dark case,
glowing blue digits, format `H:MM:SS` where the hour count keeps growing
past 99 (so "970:21:12" is a valid, expected display for a far-off date).

## How it works

- The countdown is rendered with Android's built-in `Chronometer` view in
  **count-down mode**. Once the widget sets the target, the actual
  second-by-second ticking happens inside your launcher's process — there is
  no background service, no polling, and essentially zero battery cost.
- A `WidgetConfigureActivity` opens automatically the first time you place
  the widget (Android requires this for any widget with a configure step),
  and again any time you **tap the widget** afterward, so you can change the
  target date or label.
- `BootReceiver` re-syncs the countdown after every phone restart, since the
  clock `Chronometer` uses internally (`elapsedRealtime`) resets at boot.
- An exact alarm is scheduled for the target moment so the widget flips to
  "EVENT REACHED" right on time instead of waiting for Android's next
  30-minute widget refresh window (30 min is the OS-enforced minimum for
  `updatePeriodMillis`; this app only uses that as a safety-net resync).

## Opening the project

1. Open Android Studio → **Open** → select the `LEDCountdownWidget` folder
   (the one containing `settings.gradle`).
2. Let Gradle sync (first sync will download Gradle 8.7 + AGP automatically
   — needs internet once).
3. Run on a device/emulator, **or** build → `Build > Build Bundle(s)/APK(s) >
   Build APK(s)` to get an installable `.apk` under
   `app/build/outputs/apk/debug/`.

## Adding the widget to your home screen

Long-press an empty spot on your home screen → **Widgets** → find
**LED Countdown** → drag it out → the configure screen opens → pick a date,
time, and optional label → **Save**.

## Customizing the look

- Colors: `app/src/main/res/values/colors.xml`
- Widget size/aspect: `app/src/main/res/xml/countdown_widget_info.xml`
  (`minWidth` / `minHeight`)
- Text size / spacing / case shape: `app/src/main/res/layout/countdown_widget.xml`

### Using a real 7-segment font (optional, closer to the photo)

The layout currently uses `monospace` + bold + letter-spacing to fake a
digital look without bundling any binary font files. For an exact 7-segment
match:

1. Download an open-license 7-segment font, e.g. **DSEG** (SIL Open Font
   License) from `https://github.com/keshikan/DSEG`.
2. Put the `.ttf` file in `app/src/main/res/font/dseg7_classic.ttf`
   (create the `font` folder if it isn't there).
3. In `countdown_widget.xml`, replace `android:fontFamily="monospace"` with
   `android:fontFamily="@font/dseg7_classic"` on both the `Chronometer` and
   the "reached" `TextView`.

## Changing the package name / app id

Currently `com.homelab.ledcountdown` in both `app/build.gradle`
(`applicationId`, `namespace`) and `AndroidManifest.xml`/Kotlin `package`
declarations. Android Studio's **Refactor → Rename** on the package in the
project tree will update all of these consistently if you want to change it.

## Notes on personal-use signing

For your own device this debug build is enough — Android Studio signs debug
APKs automatically with a local debug key so you can install and run it. You
only need a release keystore if you ever plan to distribute it beyond your
own devices.
