"""The colours of Daftarche (the desktop app's style.py), for a dark and a light phone."""

from __future__ import annotations

from dataclasses import dataclass

import flet as ft


@dataclass(frozen=True)
class Palette:
    accent: str
    bg: str
    surface: str
    raised: str
    text: str
    dim: str
    border: str
    income: str
    expense: str
    transfer: str

    def kind(self, kind):
        """The colour of Income, Expense or Transfer."""
        return {"Income": self.income, "Expense": self.expense, "Transfer": self.transfer}.get(kind, self.dim)

    def signed(self, value):
        """Green for more than 0, red for less."""
        return self.income if value > 0 else self.expense if value < 0 else self.text


DARK = Palette(accent="#7c6af7", bg="#1e1c18", surface="#2a2720", raised="#38342e", text="#e8e0d0",
               dim="#9a9080", border="#4a4338", income="#2ecc71", expense="#e74c3c", transfer="#f39c12")
LIGHT = Palette(accent="#6b57e8", bg="#f5f3ee", surface="#ffffff", raised="#e9e5dc", text="#2a2620",
                dim="#7a7064", border="#d4ccbe", income="#1f9d55", expense="#d33a2c", transfer="#c97a06")

THEME_CHOICES = (("system", "Phone", ft.Icons.SMARTPHONE), ("light", "Light", ft.Icons.LIGHT_MODE),
                 ("dark", "Dark", ft.Icons.DARK_MODE))
"""Settings › Appearance, as in Vahid's other phone apps: (stored value, label, icon)."""

FONT = "Plex"
"""IBM Plex Sans (assets/IBMPlexSans.ttf, SIL Open Font License), the font of all three phone apps."""
FONT_FILES = {FONT: "IBMPlexSans.ttf"}


def palette_for(choice, brightness):
    """The palette for the theme chosen in the app ("system" follows the phone)."""
    if choice == "dark":
        return DARK
    if choice == "light":
        return LIGHT
    return LIGHT if brightness == ft.Brightness.LIGHT else DARK


def system_bars(p: Palette):
    """Android's own bars in the app's colours: the button strip at the bottom like the tab bar, the
    status bar like the page, with light symbols on the dark theme and dark ones on the light."""
    symbols = ft.Brightness.LIGHT if p is DARK else ft.Brightness.DARK
    return ft.SystemOverlayStyle(
        system_navigation_bar_color=p.surface, system_navigation_bar_divider_color=p.surface,
        system_navigation_bar_icon_brightness=symbols, enforce_system_navigation_bar_contrast=False,
        status_bar_color=p.bg, status_bar_icon_brightness=symbols,
        status_bar_brightness=ft.Brightness.DARK if p is DARK else ft.Brightness.LIGHT,
        enforce_system_status_bar_contrast=False)


def material_theme(p: Palette):
    """A Material theme in these colours, for the controls Flet draws itself."""
    return ft.Theme(
        font_family=FONT, system_overlay_style=system_bars(p),
        color_scheme=ft.ColorScheme(primary=p.accent, on_primary="#ffffff", secondary=p.accent,
                                    surface=p.surface, on_surface=p.text, on_surface_variant=p.dim,
                                    outline=p.border, outline_variant=p.border,
                                    surface_container=p.surface, surface_container_low=p.surface,
                                    surface_container_high=p.raised, surface_container_highest=p.raised),
        scaffold_bgcolor=p.bg, canvas_color=p.surface, divider_color=p.border,
    )
