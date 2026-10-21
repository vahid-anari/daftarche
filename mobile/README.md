# Daftarche on the phone

A read-only view of your account book for Android: the four tabs of Daftarche
(Dashboard, Transactions, Charts, Accounts) and your loans, from the phone
snapshot that Daftarche on the Mac writes (`docs/phone-snapshot.md`).

The app never changes your data and does no bookkeeping of its own: balances and
loans come ready-made from the Mac, and the tests check that its sums match
Daftarche's own.

## Installing it on an Android phone

1. On the phone, open the repository's
   [Releases](https://github.com/vahid-anari/daftarche/releases), find the newest
   **Phone X.Y.Z** and tap `daftarche-phone-X.Y.Z.apk` to download it.
2. Open the downloaded file. Android asks once whether your browser may install
   apps: allow it, then tap **Install**.
3. Open Daftarche, tap **Choose Folder** and pick the folder Syncthing keeps (below).
   Android then shows **All files access** for Daftarche: turn it on and come back.
   The app only reads `daftarche-phone.json`; it never changes or sends anything.

Later versions: the app looks for one once a day (or Settings › Check for Updates)
and offers **Download**; open the file and install it over the old one. Your folder
and settings stay.

## How the data gets to the phone: Syncthing

[Syncthing](https://syncthing.net) copies a folder between the Mac and the phone
directly, with no cloud in between. Both need to be on (and online) at some point;
the phone keeps the last copy, so the app works offline.

1. **Mac:** install Syncthing (`brew install --cask syncthing`, or from syncthing.net)
   and open it. Its page opens in the browser.
2. **Phone:** install **Syncthing-Fork** (Google Play or F-Droid).
3. **Pair them:** on the Mac, *Add Remote Device* and scan or type the phone's device
   ID (Syncthing-Fork › menu › Show device ID). Accept on the phone.
4. **Share a folder:** on the Mac, *Add Folder*, e.g. `~/Daftarche-Phone`, label
   *Daftarche*, and share it with the phone. On the phone, accept it and choose
   where it goes, e.g. `/storage/emulated/0/Daftarche`. Setting the phone's copy to
   *Receive Only* is a good idea: the Mac is the one that writes.
5. **Daftarche on the Mac:** Settings › Phone › Choose… `~/Daftarche-Phone`. The file
   is written there after every import and when Daftarche closes (or File › Update
   Phone Snapshot).
6. **Daftarche on the phone:** Choose Folder › the phone's copy
   (`/storage/emulated/0/Daftarche`). If the folder picker gives no usable path, type
   it in Settings and tap **Use Typed Path**.

Coming back to the app reads the file again; the ⟳ button does it at any time.

Swipe left or right to change tabs. Android's Back goes back one step: it closes an open
sheet, returns from "Show transactions" (or an account's transactions) to where you were,
goes to the Dashboard from another tab, and on the Dashboard asks once before leaving.

## Trying it on the Mac

In an environment of its own (it needs Flet, Daftarche does not):

```zsh
conda create -n phone python=3.13 -y && conda activate phone
pip install "flet[all]==1.0.4"
cd mobile
DAFTARCHE_PHONE_FOLDER=~/Desktop/phone-test flet run src/main.py
```

`DAFTARCHE_PHONE_FOLDER` is the folder with `daftarche-phone.json`; without it the
app asks for one.

## Tests

From the repository root, in the `dev` environment (they need Daftarche, not Flet):

```zsh
pytest mobile/tests
```

## Making a release

### Once: the signing key

Every version must be signed with the same key, or Android refuses to install it
over the one before. Make it once and keep a copy somewhere safe (a password
manager, a USB stick): it cannot be made again.

```zsh
conda activate phone
conda install -c conda-forge openjdk -y     # for keytool
mkdir -p ~/Documents/daftarche-keys && cd ~/Documents/daftarche-keys
keytool -genkeypair -v -storetype PKCS12 -keystore daftarche-phone.jks -alias daftarche \
        -keyalg RSA -keysize 2048 -validity 36500 -dname "CN=Vahid Anari"
base64 -i daftarche-phone.jks | pbcopy       # the key store, copied as text
```

On GitHub, the repository › Settings › Secrets and variables › Actions › New
repository secret:

- `ANDROID_KEYSTORE_BASE64`: paste (what `pbcopy` copied).
- `ANDROID_KEYSTORE_PASSWORD`: the password you gave keytool.

### Each version

1. Raise `version` in `mobile/pyproject.toml` and `__version__` in
   `mobile/src/daftarche_phone/__init__.py` (a test checks they match).
2. Add `## X.Y.Z — date` to `mobile/CHANGELOG.md`.
3. Commit, then `git tag phone-vX.Y.Z && git push && git push --tags`.

The *phone release* workflow runs the tests, builds the signed APK (about 15
minutes) and publishes **Phone X.Y.Z** with it. It is not marked as the latest
release, so the desktop app's stays that.

## Layout

- `src/main.py`: the entry point.
- `src/daftarche_phone/snapshot.py`: reading the file and adding it up (no Flet).
- `src/daftarche_phone/app.py`: the screens.
- `src/daftarche_phone/charts.py`: bars and lines from plain controls and a canvas.
- `src/daftarche_phone/theme.py`: Daftarche's dark and light colours.
- `src/daftarche_phone/update.py`: is there a newer release (no Flet).
- `../.github/workflows/phone-release.yml`: builds and publishes the APK.

This folder is not part of the `daftarche` package on PyPI.
