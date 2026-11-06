"""0.35.6: the icon window has two columns, emoji on the left and logos & pictures on the right
(found by name); a picture of its own can be added (a file, a website) and deleted. The lists to
choose a category, sub-category or merchant show their icons, the Transactions filters too."""

from unittest import mock

import pytest

from conftest import keep


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def png(colour, side=64):
    from PySide6.QtGui import QColor, QImage

    from daftarche.logos import to_png
    image = QImage(side, side, QImage.Format_ARGB32)
    image.fill(QColor(colour))
    return to_png(image)


def test_pictures_in_the_database(db):
    from daftarche.db import clean_icon
    pid = db.add_picture("pcb", png("#004d40"))
    assert db.get_pictures()[pid][0] == "pcb" and db.picture(pid)
    assert clean_icon(f"pic:{pid}") == f"pic:{pid}"
    with pytest.raises(ValueError):
        clean_icon("pic:x")
    db.add_category("Hobbies", "Expense")
    cat = db.get_category_by_name("Hobbies", type_name="Expense")
    db.set_category_icon(cat["id"], f"pic:{pid}")
    assert db.picture_uses(pid) == 1
    db.delete_picture(pid)
    assert db.get_pictures() == {} and db.get_category_by_name("Hobbies", type_name="Expense")["icon"] is None


def test_the_phone_gets_the_picture(db):
    """0.37: it goes to the phone too (before, the phone showed no icon for it)."""
    from daftarche.phone import build_snapshot
    pid = db.add_picture("pcb", png("#004d40"))
    db.add_category("Hobbies", "Expense")
    cat = db.get_category_by_name("Hobbies", type_name="Expense")
    db.set_category_icon(cat["id"], f"pic:{pid}")
    snap = build_snapshot(db)
    hobbies = next(c for c in snap["categories"] if c["name"] == "Hobbies")
    assert (hobbies["icon"], hobbies["image"]) == (None, f"pic:{pid}") and f"pic:{pid}" in snap["images"]


def test_the_window_two_columns_add_find_cancel(qapp, db, tmp_path):
    from daftarche.icons import IconPickerDialog, use_logos
    use_logos(db)
    db.set_logo("Maple Grocer", png("#2e7d32"))
    db.set_logo("Quick Cab", png("#fdd835"))
    d = keep(IconPickerDialog("", "Category", name="Hobbies", db=db))
    assert set(d._logo_buttons) == {"logo:Maple Grocer", "logo:Quick Cab"}
    d.find_logo.setText("quick")
    assert set(d._logo_buttons) == {"logo:Quick Cab"}
    picture = tmp_path / "board.png"
    picture.write_bytes(png("#004d40", 200))
    with mock.patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(picture), "")):
        d._choose_picture()
    pid = next(iter(db.get_pictures()))
    assert d.icon == f"pic:{pid}" and f"pic:{pid}" in d._logo_buttons and d.find_logo.text() == ""
    assert d.typed.text() == ""  # a picture is no text for the paste field
    d.reject()  # Cancel: the picture added here is gone again
    assert db.get_pictures() == {}
    d2 = keep(IconPickerDialog("", "Category", name="Hobbies", db=db))
    with mock.patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(picture), "")):
        d2._choose_picture()
    d2._accept()
    assert d2.icon.startswith("pic:") and len(db.get_pictures()) == 1  # OK: kept


def test_delete_a_picture_in_use(qapp, db):
    from PySide6.QtWidgets import QMessageBox

    from daftarche.icons import IconPickerDialog, use_logos
    use_logos(db)
    pid = db.add_picture("mine", png("#123456"))
    db.add_category("Hobbies", "Expense")
    cat = db.get_category_by_name("Hobbies", type_name="Expense")
    db.set_category_icon(cat["id"], f"pic:{pid}")
    d = keep(IconPickerDialog(f"pic:{pid}", "Category", name="Hobbies", db=db))
    button = d._logo_buttons[f"pic:{pid}"]
    delete = mock.Mock()
    menu = mock.Mock(addAction=mock.Mock(return_value=delete), exec=mock.Mock(return_value=delete))
    with mock.patch("PySide6.QtWidgets.QMenu", return_value=menu), \
            mock.patch("daftarche.icons.QMessageBox.question", return_value=QMessageBox.Yes) as asked:
        d._picture_menu(f"pic:{pid}", button)
    assert "1 category has it" in asked.call_args.args[2]
    assert db.get_pictures() == {} and d.icon == ""


def test_paste_field_has_the_usual_font(qapp, db):
    from daftarche.icons import IconPickerDialog
    d = keep(IconPickerDialog("🛒", "Category", name="Groceries"))
    assert "font-size" not in d.typed.styleSheet()


def test_lists_show_icons(qapp, db):
    from daftarche.icons import merchant_icon_for, name_icon_for, set_merchant_icons
    from daftarche.widgets import CheckComboBox
    from PySide6.QtWidgets import QComboBox
    db.set_logo("Maple Grocer", png("#2e7d32"))
    db.set_person("Ali")
    db.add_category("Food", "Expense")
    food = db.get_category_by_name("Food", type_name="Expense")
    db.set_category_icon(food["id"], "🍔")
    combo = QComboBox()
    combo.addItems(["Maple Grocer", "Ali", "Plain Shop"])
    set_merchant_icons(combo, db)
    assert all(not combo.itemIcon(i).isNull() for i in range(3))  # a logo, 👤, a space
    check = keep(CheckComboBox("All"))
    check.icon_for = lambda: name_icon_for(db, "cat")
    check.populate(["Food", "Other"])
    assert not check._list.item(0).icon().isNull()
    assert merchant_icon_for(db)("Maple Grocer") is not None


def test_a_combo_one_types_in_shows_icons_in_its_list_only(qapp, db):
    """Typed or set as text, the name keeps no other merchant's logo beside it."""
    from PySide6.QtWidgets import QStyleOptionViewItem

    from daftarche.icons import _ListIcons, set_merchant_icons
    from daftarche.widgets import SingleSelectCombo
    db.set_logo("Amazon", png("#c62828"))
    combo = keep(SingleSelectCombo())
    combo.allow_typing()
    combo.addItems(["Amazon", "Costco"])
    set_merchant_icons(combo, db)
    combo.setCurrentText("Costco")
    assert combo.itemIcon(0).isNull()  # nothing beside the text in the field
    delegate = combo.itemDelegate()
    assert isinstance(delegate, _ListIcons)
    option = QStyleOptionViewItem()
    delegate.initStyleOption(option, combo.model().index(0, 0))
    assert not option.icon.isNull()  # in the list: Amazon's logo


def test_the_window_grows_with_more_in_a_line(qapp, db):
    """Wider: more emoji in a line (not wider gaps); taller: more lines in sight."""
    from daftarche.icons import IconPickerDialog
    d = keep(IconPickerDialog("", "Category", name="Food", db=db))
    d.show()
    for _ in range(5):
        qapp.processEvents()
    first = d._buttons[next(iter(d._buttons))]
    def in_first_line():
        return sum(1 for b in d._buttons.values() if b.y() == first.y())
    small, tall = in_first_line(), d.emoji_area.viewport().height()
    d.resize(d.width() + 300, d.height() + 200)
    for _ in range(5):
        qapp.processEvents()
    assert in_first_line() > small and d.emoji_area.viewport().height() > tall
    gaps = sorted({b.x() for b in d._buttons.values()})
    assert gaps[1] - gaps[0] == 46 + 4  # the same gap


def test_a_picture_from_a_website_in_the_window(qapp, db):
    from daftarche.icons import IconPickerDialog
    d = keep(IconPickerDialog("", "Category", name="Parts", db=db))
    with mock.patch("daftarche.logos.fetch_within", return_value=(png("#004d40"), "https://digikey.ca/icon.png")):
        d.site.setText("digikey.ca")
        d._picture_from_web()
        import time
        for _ in range(200):
            qapp.processEvents()
            if not d.web_busy():
                break
            time.sleep(0.01)
            d._web_collect()
    pid, (name, _image) = next(iter(db.get_pictures().items()))
    assert name == "digikey.ca" and d.icon == f"pic:{pid}" and d.btn_site.text() == "Get"
