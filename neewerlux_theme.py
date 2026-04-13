"""Theme System for NeewerLux.

Provides clean dark and light QSS stylesheets optimized for readability.
Accent colors are kept subtle — user-customizable themes planned for a future release.
"""

# Default accent colors (subtle, readable)
ACCENT = "#5b8def"
ACCENT_HOVER = "#7aa5f7"
ACCENT_DIM = "#3d6bc7"
SUCCESS = "#4caf50"
DANGER = "#e05555"

DARK_QSS = """
/* === DARK THEME === */
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #d4d4d8;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 10pt;
}
QPushButton {
    background-color: #2a2a3c; border: 1px solid #3c3c50;
    border-radius: 4px; color: #d4d4d8; padding: 6px 14px; min-height: 22px;
}
QPushButton:hover { border-color: #5b8def; background-color: #32324a; }
QPushButton:pressed { background-color: #5b8def; color: white; }
QPushButton:disabled { background-color: #252535; color: #555568; border-color: #303040; }
QPushButton#httpToggleBtn { padding: 4px 10px; font-size: 9pt; border: 1px solid #555568; color: #888; }
QPushButton#httpToggleBtn[httpActive="true"] { border-color: #4caf50; color: #4caf50; }
QPushButton#themeToggleBtn { padding: 4px 10px; font-size: 12pt; border: 1px solid #555568; }
QTableWidget {
    background-color: #1e1e2e; alternate-background-color: #24243a;
    border: 1px solid #3c3c50; gridline-color: #303045; color: #d4d4d8;
    selection-background-color: #3a4a6a; selection-color: #e8e8f0;
}
QTableWidget::item { padding: 4px 6px; }
QTableWidget::item:selected { background-color: #3a4a6a; }
QHeaderView::section {
    background-color: #262640; color: #5b8def;
    border: 1px solid #3c3c50; padding: 4px 6px; font-weight: bold; font-size: 9pt;
}
QHeaderView::section:vertical { background-color: #262640; color: #888; font-weight: bold; min-width: 28px; }
QTabWidget::pane { border: 1px solid #3c3c50; background-color: #1e1e2e; }
QTabBar::tab {
    background-color: #24243a; border: 1px solid #3c3c50; border-bottom: none;
    border-top-left-radius: 4px; border-top-right-radius: 4px;
    padding: 6px 14px; margin-right: 2px; color: #8888a0;
}
QTabBar::tab:selected { background-color: #1e1e2e; color: #5b8def; border-bottom: 2px solid #5b8def; }
QTabBar::tab:hover:!selected { background-color: #2a2a44; color: #b0b0c0; }
QTabBar::tab:disabled { color: #444455; }
QSlider::groove:horizontal { height: 6px; background: #303045; border-radius: 3px; }
QSlider::handle:horizontal {
    background: #5b8def; border: 2px solid #3d6bc7;
    width: 16px; height: 16px; margin: -6px 0; border-radius: 9px;
}
QSlider::handle:horizontal:hover { background: #7aa5f7; border-color: #5b8def; }
QSlider::sub-page:horizontal { background: #5b8def; border-radius: 3px; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {
    background-color: #24243a; border: 1px solid #3c3c50; border-radius: 3px;
    color: #d4d4d8; padding: 4px 6px; selection-background-color: #5b8def;
}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #5b8def; }
QComboBox::drop-down { border-left: 1px solid #3c3c50; width: 20px; subcontrol-origin: padding; subcontrol-position: center right; }
QComboBox::down-arrow { width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid #8888aa; }
QComboBox QAbstractItemView {
    background-color: #24243a; border: 1px solid #3c3c50; color: #d4d4d8;
    selection-background-color: #3a4a6a;
}
QScrollBar:vertical { background: #1e1e2e; width: 10px; border: none; }
QScrollBar::handle:vertical { background: #3c3c55; border-radius: 5px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background: #505068; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; border: none; height: 0px; }
QScrollBar:horizontal { background: #1e1e2e; height: 10px; border: none; }
QScrollBar::handle:horizontal { background: #3c3c55; border-radius: 5px; min-width: 20px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; border: none; width: 0px; }
QCheckBox { color: #d4d4d8; spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #555568; border-radius: 3px; background-color: #24243a; }
QCheckBox::indicator:checked { background-color: #5b8def; border-color: #5b8def; }
QLabel { color: #d4d4d8; }
QToolTip { background-color: #2a2a44; border: 1px solid #5b8def; color: #e0e0e8; padding: 6px 8px; border-radius: 4px; font-size: 9pt; }
QStatusBar { background-color: #18182a; color: #5b8def; font-size: 9pt; border-top: 1px solid #303045; }
QMenuBar { background-color: #1e1e2e; color: #d4d4d8; border-bottom: 1px solid #303045; }
QMenuBar::item:selected { background-color: #3a4a6a; }
QMenu { background-color: #24243a; border: 1px solid #3c3c50; color: #d4d4d8; }
QMenu::item:selected { background-color: #3a4a6a; }
QPushButton[presetButton="true"] {
    background-color: #24243a; border: 1px solid #3c3c55; border-radius: 4px;
    color: #b0b0c0; font-size: 8pt; min-height: 55px;
}
QPushButton[presetButton="true"]:hover { border-color: #5b8def; background-color: #2e2e48; }
QPushButton[presetButton="true"]:pressed { background-color: #5b8def; color: white; }
QPushButton[presetType="global"] { background-color: #252548; border: 1px solid #5b8def; color: #a0b8e8; }
QPushButton[presetType="global"]:hover { background-color: #303060; border-color: #7aa5f7; }
QPushButton[presetType="snap"] { background-color: #1e3828; border: 1px solid #4caf50; color: #a0d8a8; }
QPushButton[presetType="snap"]:hover { background-color: #284838; border-color: #66cc6a; }
QPushButton[activeScene="true"] { background-color: #1e3828; border: 1px solid #4caf50; color: #4caf50; }
QPushButton#applyButton { background-color: #2a4060; border: 1px solid #5b8def; color: #c0d8ff; font-weight: bold; font-size: 11pt; }
QPushButton#applyButton:hover { background-color: #3a5078; border-color: #7aa5f7; }
QSplitter::handle { background-color: #303050; height: 3px; width: 3px; }
QSplitter::handle:hover { background-color: #5b8def; }
QGroupBox { border: 1px solid #3c3c50; border-radius: 4px; margin-top: 8px; padding-top: 8px; color: #d4d4d8; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #5b8def; }
QListWidget { background-color: #1e1e2e; border: 1px solid #3c3c50; color: #d4d4d8; alternate-background-color: #24243a; }
QListWidget::item:selected { background-color: #3a4a6a; }
QListWidget::item:hover { background-color: #2a2a44; }
QKeySequenceEdit { background-color: #24243a; border: 1px solid #3c3c50; color: #d4d4d8; padding: 3px; }
QProgressBar { border: 1px solid #3c3c50; border-radius: 3px; text-align: center; background-color: #1e1e2e; color: #d4d4d8; }
QProgressBar::chunk { background-color: #5b8def; border-radius: 2px; }
QGraphicsView { border: none; }
"""

LIGHT_QSS = """
/* === LIGHT THEME === */
QMainWindow, QWidget {
    background-color: #f5f5f8; color: #2a2a3a;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif; font-size: 10pt;
}
QPushButton {
    background-color: #e8e8f0; border: 1px solid #c0c0d0;
    border-radius: 4px; color: #2a2a3a; padding: 6px 14px; min-height: 22px;
}
QPushButton:hover { border-color: #4a7fd8; background-color: #dce4f0; }
QPushButton:pressed { background-color: #4a7fd8; color: white; }
QPushButton:disabled { background-color: #e8e8ec; color: #a0a0b0; border-color: #d0d0d8; }
QPushButton#httpToggleBtn { padding: 4px 10px; font-size: 9pt; border: 1px solid #c0c0d0; color: #888; }
QPushButton#httpToggleBtn[httpActive="true"] { border-color: #4caf50; color: #2e8b32; }
QPushButton#themeToggleBtn { padding: 4px 10px; font-size: 12pt; border: 1px solid #c0c0d0; }
QTableWidget {
    background-color: #ffffff; alternate-background-color: #f0f0f5;
    border: 1px solid #c0c0d0; gridline-color: #dcdce0; color: #2a2a3a;
    selection-background-color: #d0ddf5; selection-color: #1a1a2a;
}
QTableWidget::item { padding: 4px 6px; }
QTableWidget::item:selected { background-color: #d0ddf5; }
QHeaderView::section {
    background-color: #e0e0ea; color: #4a7fd8;
    border: 1px solid #c0c0d0; padding: 4px 6px; font-weight: bold; font-size: 9pt;
}
QHeaderView::section:vertical { background-color: #e0e0ea; color: #666; font-weight: bold; min-width: 28px; }
QTabWidget::pane { border: 1px solid #c0c0d0; background-color: #f5f5f8; }
QTabBar::tab {
    background-color: #e0e0e8; border: 1px solid #c0c0d0; border-bottom: none;
    border-top-left-radius: 4px; border-top-right-radius: 4px;
    padding: 6px 14px; margin-right: 2px; color: #6a6a80;
}
QTabBar::tab:selected { background-color: #f5f5f8; color: #4a7fd8; border-bottom: 2px solid #4a7fd8; }
QTabBar::tab:hover:!selected { background-color: #d8d8e4; color: #3a3a50; }
QTabBar::tab:disabled { color: #b0b0bc; }
QSlider::groove:horizontal { height: 6px; background: #d0d0d8; border-radius: 3px; }
QSlider::handle:horizontal {
    background: #4a7fd8; border: 2px solid #3a6ab8;
    width: 16px; height: 16px; margin: -6px 0; border-radius: 9px;
}
QSlider::handle:horizontal:hover { background: #5a8fe8; border-color: #4a7fd8; }
QSlider::sub-page:horizontal { background: #4a7fd8; border-radius: 3px; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {
    background-color: #ffffff; border: 1px solid #c0c0d0; border-radius: 3px;
    color: #2a2a3a; padding: 4px 6px; selection-background-color: #4a7fd8; selection-color: white;
}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #4a7fd8; }
QComboBox::drop-down { border-left: 1px solid #c0c0d0; width: 20px; subcontrol-origin: padding; subcontrol-position: center right; }
QComboBox::down-arrow { width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid #555566; }
QComboBox QAbstractItemView { background-color: #ffffff; border: 1px solid #c0c0d0; color: #2a2a3a; selection-background-color: #d0ddf5; }
QScrollBar:vertical { background: #f0f0f5; width: 10px; border: none; }
QScrollBar::handle:vertical { background: #c0c0d0; border-radius: 5px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background: #a0a0b8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; border: none; height: 0px; }
QScrollBar:horizontal { background: #f0f0f5; height: 10px; border: none; }
QScrollBar::handle:horizontal { background: #c0c0d0; border-radius: 5px; min-width: 20px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; border: none; width: 0px; }
QCheckBox { color: #2a2a3a; spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #b0b0c0; border-radius: 3px; background-color: #ffffff; }
QCheckBox::indicator:checked { background-color: #4a7fd8; border-color: #4a7fd8; }
QLabel { color: #2a2a3a; }
QToolTip { background-color: #ffffff; border: 1px solid #4a7fd8; color: #2a2a3a; padding: 6px 8px; border-radius: 4px; font-size: 9pt; }
QStatusBar { background-color: #e8e8f0; color: #4a7fd8; font-size: 9pt; border-top: 1px solid #c0c0d0; }
QMenuBar { background-color: #f5f5f8; color: #2a2a3a; border-bottom: 1px solid #c0c0d0; }
QMenuBar::item:selected { background-color: #d0ddf5; }
QMenu { background-color: #ffffff; border: 1px solid #c0c0d0; color: #2a2a3a; }
QMenu::item:selected { background-color: #d0ddf5; }
QPushButton[presetButton="true"] {
    background-color: #e8e8f0; border: 1px solid #c0c0d0; border-radius: 4px;
    color: #3a3a50; font-size: 8pt; min-height: 55px;
}
QPushButton[presetButton="true"]:hover { border-color: #4a7fd8; background-color: #dce4f0; }
QPushButton[presetButton="true"]:pressed { background-color: #4a7fd8; color: white; }
QPushButton[presetType="global"] { background-color: #d8e4f8; border: 1px solid #5b8def; color: #2a3a5a; }
QPushButton[presetType="global"]:hover { background-color: #c8d8f0; border-color: #4a7fd8; }
QPushButton[presetType="snap"] { background-color: #d8f0e0; border: 1px solid #4caf50; color: #1e3a22; }
QPushButton[presetType="snap"]:hover { background-color: #c8e8d0; border-color: #3e9842; }
QPushButton[activeScene="true"] { background-color: #d8f0e0; border: 1px solid #4caf50; color: #2e8b32; }
QPushButton#applyButton { background-color: #d0ddf5; border: 1px solid #4a7fd8; color: #2a3a5a; font-weight: bold; font-size: 11pt; }
QPushButton#applyButton:hover { background-color: #c0d0f0; border-color: #3a6ab8; }
QSplitter::handle { background-color: #c0c0d0; height: 3px; width: 3px; }
QSplitter::handle:hover { background-color: #4a7fd8; }
QGroupBox { border: 1px solid #c0c0d0; border-radius: 4px; margin-top: 8px; padding-top: 8px; color: #2a2a3a; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #4a7fd8; }
QListWidget { background-color: #ffffff; border: 1px solid #c0c0d0; color: #2a2a3a; alternate-background-color: #f0f0f5; }
QListWidget::item:selected { background-color: #d0ddf5; }
QListWidget::item:hover { background-color: #e8ecf5; }
QKeySequenceEdit { background-color: #ffffff; border: 1px solid #c0c0d0; color: #2a2a3a; padding: 3px; }
QProgressBar { border: 1px solid #c0c0d0; border-radius: 3px; text-align: center; background-color: #f0f0f5; color: #2a2a3a; }
QProgressBar::chunk { background-color: #4a7fd8; border-radius: 2px; }
QGraphicsView { border: none; }
"""


def getThemeQSS(isDark=True):
    """Return the QSS for the requested theme."""
    return DARK_QSS if isDark else LIGHT_QSS
