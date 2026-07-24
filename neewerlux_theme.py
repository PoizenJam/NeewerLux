"""Theme tokens and stylesheet generation for NeewerLux.

Both themes come from one template, so a styling change is made once.
To restyle, edit the token tables below rather than the template.

The palette is deliberately desaturated. This app is used to judge colour
temperature and hue, and saturated chrome biases that judgement. Changing
"accent" in both tables is enough to re-tint the whole interface.
"""

from string import Template

# Geometry, shared by both themes.
RADIUS_SM = "3px"      # inputs, small chips
RADIUS_MD = "4px"      # buttons, tabs, cards
RADIUS_SLIDER = "9px"  # half the 18px slider handle, must stay circular
RADIUS_SCROLL = "5px"  # half the 10px scrollbar, must stay circular

PAD_INPUT = "4px 6px"
PAD_BUTTON = "6px 14px"
PAD_BUTTON_SM = "4px 10px"
PAD_TOOLTIP = "6px 8px"

FONT_UI = '"Segoe UI", "Helvetica Neue", sans-serif'
FONT_MONO = '"Consolas", "Menlo", "DejaVu Sans Mono", monospace'
FONT_SIZE = "10pt"
FONT_SIZE_SM = "9pt"

DARK = {
    # surfaces, deepest to lightest
    "bg0": "#18182a",   # status bar and deepest chrome
    "bg1": "#1e1e2e",   # window, tables, lists
    "bg2": "#24243a",   # inputs, alternate rows, tabs
    "bg3": "#2c2c42",   # raised buttons
    "bg4": "#34344e",   # hover
    "border": "#3c3c50",
    "borderStrong": "#55556a",
    # text
    "text": "#d4d4d8",
    "textDim": "#8f8fa5",
    "textFaint": "#5a5a70",
    # accent
    "accent": "#5b8def",
    "accentHover": "#7aa5f7",
    "accentDim": "#3d6bc7",
    "accentSoft": "#3a4a6a",
    "accentWash": "#2a4060",
    "accentWashHover": "#3a5078",
    "accentText": "#c0d8ff",
    "onAccent": "#ffffff",
    # preset variants
    "globalWash": "#252548",
    "globalWashHover": "#303060",
    "globalText": "#a0b8e8",
    # semantic
    "success": "#4caf50",
    "successText": "#4caf50",
    "successHover": "#66cc6a",
    "successWash": "#1e3828",
    "successWashHover": "#284838",
    "danger": "#e05555",
    # incidental
    "selectionText": "#e8e8f0",
}

LIGHT = {
    "bg0": "#e8e8f0",
    "bg1": "#f5f5f8",
    "bg2": "#ffffff",
    "bg3": "#e8e8f0",
    "bg4": "#dce4f0",
    "border": "#c0c0d0",
    "borderStrong": "#a8a8bc",
    "text": "#2a2a3a",
    "textDim": "#6a6a80",
    "textFaint": "#a0a0b0",
    "accent": "#4a7fd8",
    "accentHover": "#5a8fe8",
    "accentDim": "#3a6ab8",
    "accentSoft": "#d0ddf5",
    "accentWash": "#d0ddf5",
    "accentWashHover": "#c0d0f0",
    "accentText": "#2a3a5a",
    "globalWash": "#d0ddf5",
    "globalWashHover": "#c0d0f0",
    "onAccent": "#ffffff",
    "globalText": "#2a3a5a",
    "success": "#4caf50",
    "successText": "#2e8b32",
    "successHover": "#3e9842",
    "successWash": "#d8f0e0",
    "successWashHover": "#c8e8d0",
    "danger": "#e05555",
    "selectionText": "#1a1a2a",
}

_TEMPLATE = Template("""
QMainWindow, QWidget {
    background-color: $bg1;
    color: $text;
    font-family: $fontUI;
    font-size: $fontSize;
}
QPushButton {
    background-color: $bg3; border: 1px solid $border;
    border-radius: $radiusMd; color: $text; padding: $padButton; min-height: 22px;
}
QPushButton:hover { border-color: $accent; background-color: $bg4; }
QPushButton:pressed { background-color: $accent; color: $onAccent; }
QPushButton:disabled { background-color: $bg2; color: $textFaint; border-color: $border; }
QPushButton#httpToggleBtn { padding: $padButtonSm; font-size: $fontSizeSm; border: 1px solid $borderStrong; color: $textDim; }
QPushButton#httpToggleBtn[httpActive="true"] { border-color: $success; color: $successText; }
QPushButton#themeToggleBtn { padding: $padButtonSm; font-size: 12pt; border: 1px solid $borderStrong; }
QTableWidget {
    background-color: $bg1; alternate-background-color: $bg2;
    border: 1px solid $border; gridline-color: $border; color: $text;
    selection-background-color: $accentSoft; selection-color: $selectionText;
}
QTableWidget::item { padding: $padInput; }
QTableWidget::item:selected { background-color: $accentSoft; }
QHeaderView::section {
    background-color: $bg2; color: $accent;
    border: 1px solid $border; padding: $padInput; font-weight: bold; font-size: $fontSizeSm;
}
QHeaderView::section:vertical { background-color: $bg2; color: $textDim; font-weight: bold; min-width: 28px; }
QTabWidget::pane { border: 1px solid $border; background-color: $bg1; }
QTabBar::tab {
    background-color: $bg2; border: 1px solid $border; border-bottom: none;
    border-top-left-radius: $radiusMd; border-top-right-radius: $radiusMd;
    padding: $padButton; margin-right: 2px; color: $textDim;
}
QTabBar::tab:selected { background-color: $bg1; color: $accent; border-bottom: 2px solid $accent; }
QTabBar::tab:hover:!selected { background-color: $bg4; color: $text; }
QTabBar::tab:disabled { color: $textFaint; }
QSlider::groove:horizontal { height: 6px; background: $bg4; border-radius: $radiusSm; }
QSlider::handle:horizontal {
    background: $accent; border: 2px solid $accentDim;
    width: 16px; height: 16px; margin: -6px 0; border-radius: $radiusSlider;
}
QSlider::handle:horizontal:hover { background: $accentHover; border-color: $accent; }
QSlider::sub-page:horizontal { background: $accent; border-radius: $radiusSm; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {
    background-color: $bg2; border: 1px solid $border; border-radius: $radiusSm;
    color: $text; padding: $padInput; selection-background-color: $accent; selection-color: $onAccent;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: $accent; }
QComboBox::drop-down { border-left: 1px solid $border; width: 20px; subcontrol-origin: padding; subcontrol-position: center right; }
QComboBox::down-arrow { width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 6px solid $textDim; }
QComboBox QAbstractItemView {
    background-color: $bg2; border: 1px solid $border; color: $text;
    selection-background-color: $accentSoft;
}
QScrollBar:vertical { background: $bg1; width: 10px; border: none; }
QScrollBar::handle:vertical { background: $border; border-radius: $radiusScroll; min-height: 20px; }
QScrollBar::handle:vertical:hover { background: $borderStrong; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; border: none; height: 0px; }
QScrollBar:horizontal { background: $bg1; height: 10px; border: none; }
QScrollBar::handle:horizontal { background: $border; border-radius: $radiusScroll; min-width: 20px; }
QScrollBar::handle:horizontal:hover { background: $borderStrong; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; border: none; width: 0px; }
QCheckBox { color: $text; spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid $borderStrong; border-radius: $radiusSm; background-color: $bg2; }
QCheckBox::indicator:checked { background-color: $accent; border-color: $accent; }
QLabel { color: $text; }
QToolTip { background-color: $bg3; border: 1px solid $accent; color: $text; padding: $padTooltip; border-radius: $radiusMd; font-size: $fontSizeSm; }
QStatusBar { background-color: $bg0; color: $accent; font-size: $fontSizeSm; border-top: 1px solid $border; }
QMenuBar { background-color: $bg1; color: $text; border-bottom: 1px solid $border; }
QMenuBar::item:selected { background-color: $accentSoft; }
QMenu { background-color: $bg2; border: 1px solid $border; color: $text; }
QMenu::item:selected { background-color: $accentSoft; }
QPushButton[presetButton="true"] {
    background-color: $bg2; border: 1px solid $border; border-radius: $radiusMd;
    color: $text; font-size: 8pt; min-height: 55px;
}
QPushButton[presetButton="true"]:hover { border-color: $accent; background-color: $bg4; }
QPushButton[presetButton="true"]:pressed { background-color: $accent; color: $onAccent; }
QPushButton[presetType="global"] { background-color: $globalWash; border: 1px solid $accent; color: $globalText; }
QPushButton[presetType="global"]:hover { background-color: $globalWashHover; border-color: $accentHover; }
QPushButton[presetType="snap"] { background-color: $successWash; border: 1px solid $success; color: $successText; }
QPushButton[presetType="snap"]:hover { background-color: $successWashHover; border-color: $successHover; }
QPushButton[activeScene="true"] { background-color: $successWash; border: 1px solid $success; color: $successText; }
QPushButton#applyButton { background-color: $accentWash; border: 1px solid $accent; color: $accentText; font-weight: bold; font-size: 11pt; }
QPushButton#applyButton:hover { background-color: $accentWashHover; border-color: $accentHover; }
QSplitter::handle { background-color: $border; height: 3px; width: 3px; }
QSplitter::handle:hover { background-color: $accent; }
QGroupBox { border: 1px solid $border; border-radius: $radiusMd; margin-top: 8px; padding-top: 8px; color: $text; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: $accent; }
QListWidget { background-color: $bg1; border: 1px solid $border; color: $text; alternate-background-color: $bg2; }
QListWidget::item:selected { background-color: $accentSoft; }
QListWidget::item:hover { background-color: $bg4; }
QKeySequenceEdit { background-color: $bg2; border: 1px solid $border; color: $text; padding: 3px; }
QProgressBar { border: 1px solid $border; border-radius: $radiusSm; text-align: center; background-color: $bg1; color: $text; }
QProgressBar::chunk { background-color: $accent; border-radius: $radiusSm; }
QGraphicsView { border: none; }
""")

_GEOMETRY = {
    "radiusSm": RADIUS_SM,
    "radiusMd": RADIUS_MD,
    "radiusSlider": RADIUS_SLIDER,
    "radiusScroll": RADIUS_SCROLL,
    "padInput": PAD_INPUT,
    "padButton": PAD_BUTTON,
    "padButtonSm": PAD_BUTTON_SM,
    "padTooltip": PAD_TOOLTIP,
    "fontUI": FONT_UI,
    "fontSize": FONT_SIZE,
    "fontSizeSm": FONT_SIZE_SM,
}


def getThemeTokens(isDark=True):
    """Return the colour token table for the requested theme."""
    return DARK if isDark else LIGHT


def getThemeQSS(isDark=True):
    """Return the QSS for the requested theme."""
    return _TEMPLATE.substitute(dict(_GEOMETRY, **getThemeTokens(isDark)))
