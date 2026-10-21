# Daftarche on the phone

A read-only view of your account book for Android: the four tabs of Daftarche
(Dashboard, Transactions, Charts, Accounts) and your loans, from the phone
snapshot that Daftarche on the Mac sends it (`docs/phone-snapshot.md`).

The app never changes your data and does no bookkeeping of its own: balances and
loans come ready-made from the Mac, and the tests check that its sums match
Daftarche's own.

<img src="https://raw.githubusercontent.com/vahid-anari/daftarche/main/docs/figures/phone_dashboard.png" width="200" alt="Dashboard: total balance, accounts, this month's numbers">
<img src="https://raw.githubusercontent.com/vahid-anari/daftarche/main/docs/figures/phone_donut.png" width="200" alt="Dashboard: this month's expense by category as a donut">
<img src="https://raw.githubusercontent.com/vahid-anari/daftarche/main/docs/figures/phone_transactions.png" width="200" alt="Transactions of this month">

<img src="https://raw.githubusercontent.com/vahid-anari/daftarche/main/docs/figures/phone_transaction.png" width="200" alt="One transaction opened">
<img src="https://raw.githubusercontent.com/vahid-anari/daftarche/main/docs/figures/phone_charts.png" width="200" alt="Charts: monthly expense by category">
<img src="https://raw.githubusercontent.com/vahid-anari/daftarche/main/docs/figures/phone_accounts.png" width="200" alt="Accounts: balance by month">

The screenshots show invented data (`tools/make_demo_db.py`).

## Installing it on an Android phone

1. On the phone, open the repository's
   [Releases](https://github.com/vahid-anari/daftarche/releases), find the newest
   **Phone X.Y.Z** and tap `daftarche-phone-X.Y.Z.apk` to download it.
2. Open the downloaded file. Android asks once whether your browser may install
   apps: allow it, then tap **Install**.
3. **Connect it to your Mac:** in Daftarche on the Mac, Settings › Phone › **Sign In with
   Google…** (once), then **Connect a Phone…**. Point the phone's camera at the QR code
   it shows and tap the link: Daftarche opens on the phone, connected. If the camera won't
   open the link, press **Copy Link** on the Mac, get the text to the phone (a note, a
   message to yourself) and paste it on the app's first screen.

Later versions: the app looks for one once a day (or Settings › Check for Updates)
and offers **Download**; open the file and install it over the old one. The connection
and your settings stay.

## How the data gets to the phone: your own Google Drive

Daftarche on the Mac keeps one file per connected phone on **your** Google Drive
(it may only see the files it made itself). The file is locked with that phone's own key
before it leaves the Mac; the key travels only in the QR code, from the Mac's screen to the
phone's camera, never through Google, so Google holds nothing it can read. The phone
downloads the file by its link, without signing in.

The Mac sends your changes by itself about a minute after the last one, right after an
import, and when Daftarche closes (Settings › Phone shows when, and has **Send Now**).
The phone fetches the newest copy whenever it is opened, and keeps the last one, so the
app works offline too. The Mac need not be on.

**Disconnect** (Settings › Phone on the Mac) deletes that phone's file: the phone then
says it was disconnected and removes its copy. Disconnect on the phone (its Settings)
forgets the connection there.

Coming back to the app fetches the newest copy; the ⟳ button does it at any time.

Swipe left or right to change tabs. Android's Back goes back one step: it closes an open
sheet, returns from "Show transactions" (or an account's transactions) to where you were,
goes to the Dashboard from another tab, and on the Dashboard asks once before leaving.

## Trying it on the Mac

In an environment of its own (it needs Flet, Daftarche does not):

```zsh
conda create -n phone python=3.13 -y && conda activate phone
pip install "flet[all]==1.0.4"
cd mobile
DAFTARCHE_PHONE_DATA=~/Desktop/phone-test flet run src/main.py
```

Paste a link from **Connect a Phone…** (Copy Link) on its first screen.
`DAFTARCHE_PHONE_DATA` is where the app keeps its copy (on a phone: the app's own storage).

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
- `src/daftarche_phone/snapshot.py`: reading the snapshot and adding it up (no Flet).
- `src/daftarche_phone/link.py`: the pairing link, fetching from Google Drive, the copy kept (no Flet).
- `src/daftarche_phone/seal.py`: opening the locked file (a copy of `src/daftarche/seal.py`).
- `src/daftarche_phone/app.py`: the screens.
- `src/daftarche_phone/charts.py`: bars and lines from plain controls and a canvas.
- `src/daftarche_phone/theme.py`: Daftarche's dark and light colours.
- `src/daftarche_phone/update.py`: is there a newer release (no Flet).
- `../.github/workflows/phone-release.yml`: builds and publishes the APK.

This folder is not part of the `daftarche` package on PyPI.
