# Daftarche on the phone

A read-only view of your account book for Android: the four tabs of Daftarche
(Dashboard, Transactions, Charts, Accounts) and your loans, from the phone
snapshot that Daftarche on the Mac writes (`docs/phone-snapshot.md`).

The app never changes your data and does no bookkeeping of its own: balances and
loans come ready-made from the Mac, and the tests check that its sums match
Daftarche's own.

## How the data gets to the phone

1. On the Mac, Daftarche › Settings › Phone: choose a folder that is shared with
   the phone (with Syncthing, say).
2. Daftarche writes `daftarche-phone.json` there after every import and when it
   closes (or File › Update Phone Snapshot).
3. On the phone, the app's Settings › Choose Folder: the same folder.

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

## Layout

- `src/main.py`: the entry point.
- `src/daftarche_phone/snapshot.py`: reading the file and adding it up (no Flet).
- `src/daftarche_phone/app.py`: the screens.
- `src/daftarche_phone/charts.py`: bars and lines from plain controls and a canvas.
- `src/daftarche_phone/theme.py`: Daftarche's dark and light colours.

This folder is not part of the `daftarche` package on PyPI.
