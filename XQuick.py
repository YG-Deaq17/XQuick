import os
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "XQuick"
APP_VERSION = "1.0.0"
IS_FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
DATA_DIR = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / APP_NAME if IS_FROZEN else APP_DIR
BACKUP_DIR = DATA_DIR / "backups"
RESTORE_DIR = DATA_DIR / "restored"
LOG_FILE = DATA_DIR / "logs.txt"
ICON_FILE = RESOURCE_DIR / "assets" / "XQuickIcon.ico"


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    name: str
    size: int
    created_at: datetime

    @property
    def size_label(self) -> str:
        mb = self.size / (1024 * 1024)
        return f"{mb:.1f} MB" if mb >= 1 else f"{self.size / 1024:.1f} KB"

    @property
    def date_label(self) -> str:
        return self.created_at.strftime("%d.%m.%Y %H:%M:%S")


def ensure_dirs() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    RESTORE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.touch(exist_ok=True)


def write_log(level: str, message: str) -> str:
    ensure_dirs()
    line = f"[{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}] {level.upper():<6} {message}"
    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(line + "\n")
    return line


def read_logs() -> list[str]:
    return LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()


def list_backups() -> list[BackupInfo]:
    ensure_dirs()
    items = []
    for path in BACKUP_DIR.glob("backup_*.zip"):
        stat = path.stat()
        items.append(
            BackupInfo(
                path=path,
                name=path.name,
                size=stat.st_size,
                created_at=datetime.fromtimestamp(stat.st_ctime),
            )
        )
    return sorted(items, key=lambda item: item.created_at)


def create_zip_backup(source: Path) -> BackupInfo:
    ensure_dirs()
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError("Выбранная папка или файл не найдены")

    backup_path = BACKUP_DIR / f"backup_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.zip"
    backup_root = BACKUP_DIR.resolve()

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as archive:
        if source.is_file():
            archive.write(source, source.name)
        else:
            for root, _, files in os.walk(source):
                root_path = Path(root).resolve()
                if backup_root == root_path or backup_root in root_path.parents:
                    continue
                for filename in files:
                    file_path = root_path / filename
                    archive.write(file_path, file_path.relative_to(source.parent))

    return list_backups()[-1]


def safe_extract_zip(backup: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    target_root = target.resolve()
    with zipfile.ZipFile(backup, "r") as archive:
        for member in archive.infolist():
            destination = (target / member.filename).resolve()
            if target_root != destination and target_root not in destination.parents:
                raise ValueError("Архив содержит небезопасный путь")
        archive.extractall(target)


def open_in_file_manager(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class ImpactButton(QPushButton):
    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._animation = QPropertyAnimation(self, b"geometry", self)
        self._animation.setDuration(70)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            rect = self.geometry()
            target = QRect(rect.x() + 2, rect.y() + 2, max(1, rect.width() - 4), max(1, rect.height() - 4))
            self._animate(target)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        rect = self.geometry()
        target = QRect(rect.x() - 2, rect.y() - 2, rect.width() + 4, rect.height() + 4)
        self._animate(target)
        super().mouseReleaseEvent(event)

    def _animate(self, target: QRect) -> None:
        self._animation.stop()
        self._animation.setStartValue(self.geometry())
        self._animation.setEndValue(target)
        self._animation.start()


class AppDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        title: str,
        message: str,
        kind: str = "info",
        question: bool = False,
        confirm_text: str = "Да",
        cancel_text: str = "Отмена",
        confirm_style: str = "primaryButton",
        cancel_style: str = "secondaryButton",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setObjectName("appDialog")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(18)

        row = QHBoxLayout()
        icon = QLabel({"info": "i", "warning": "!", "error": "×", "question": "?"}.get(kind, "i"))
        icon.setObjectName(f"dialogIcon_{kind}")
        icon.setFixedSize(42, 42)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text = QLabel(message)
        text.setObjectName("dialogText")
        text.setWordWrap(True)
        row.addWidget(icon)
        row.addWidget(text, 1)
        layout.addLayout(row)

        buttons = QHBoxLayout()
        buttons.setSpacing(14)
        buttons.addStretch(1)
        if question:
            no_button = make_button(cancel_text, cancel_style)
            no_button.setFixedSize(170, 54)
            no_button.clicked.connect(self.reject)
            buttons.addWidget(no_button)
            yes_button = make_button(confirm_text, confirm_style)
            yes_button.setFixedSize(170, 54)
            yes_button.clicked.connect(self.accept)
            buttons.addWidget(yes_button)
        else:
            ok_button = make_button("OK", "primaryButton")
            ok_button.clicked.connect(self.accept)
            buttons.addWidget(ok_button)
        layout.addLayout(buttons)


def show_message(parent: QWidget, message: str, kind: str = "info") -> None:
    dialog = AppDialog(parent, APP_NAME, message, kind=kind)
    dialog.exec()


def ask_question(
    parent: QWidget,
    message: str,
    confirm_text: str = "Да",
    cancel_text: str = "Отмена",
    confirm_style: str = "primaryButton",
    cancel_style: str = "secondaryButton",
) -> bool:
    dialog = AppDialog(
        parent,
        APP_NAME,
        message,
        kind="question",
        question=True,
        confirm_text=confirm_text,
        cancel_text=cancel_text,
        confirm_style=confirm_style,
        cancel_style=cancel_style,
    )
    return dialog.exec() == QDialog.DialogCode.Accepted


class XQuickWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        ensure_dirs()
        if not LOG_FILE.read_text(encoding="utf-8").strip():
            write_log("ИНФО", "Приложение запущено")

        self.source_path: Path | None = None
        self.restore_target = RESTORE_DIR
        self.backups: list[BackupInfo] = []
        self.selected_backup: BackupInfo | None = None
        self.nav_buttons: dict[str, QPushButton] = {}

        self.setWindowTitle(APP_NAME)
        if ICON_FILE.exists():
            self.setWindowIcon(QIcon(str(ICON_FILE)))
        self.resize(1440, 820)
        self.setMinimumSize(1180, 680)
        self.setAcceptDrops(True)

        self._build_ui()
        self.show_page("home")
        self.refresh_all()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_content(), 1)

        self.setStyleSheet(STYLES)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(270)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(26, 42, 22, 18)
        layout.setSpacing(12)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        logo = QLabel()
        logo.setObjectName("logoMark")
        logo.setFixedSize(32, 32)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if ICON_FILE.exists():
            logo.setPixmap(QIcon(str(ICON_FILE)).pixmap(32, 32))
        title = QLabel("XQuick")
        title.setObjectName("brand")
        brand_row.addWidget(logo)
        brand_row.addWidget(title, 1)
        layout.addLayout(brand_row)
        layout.addSpacing(14)

        for key, icon, text in [
            ("home", "⌂", "Главная"),
            ("create", "+", "Создание"),
            ("restore", "↻", "Восстановление"),
            ("logs", "▣", "Логи"),
        ]:
            button = make_button(f"{icon}   {text}", "navButton")
            button.setCheckable(True)
            button.setFixedHeight(58)
            button.clicked.connect(lambda _checked=False, page=key: self.show_page(page))
            self.nav_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        line = QFrame()
        line.setObjectName("line")
        line.setFixedHeight(1)
        layout.addWidget(line)

        folder_label = QLabel(f"▣  Папка бэкапов:\n{BACKUP_DIR}")
        folder_label.setObjectName("smallMuted")
        folder_label.setWordWrap(True)
        layout.addWidget(folder_label)

        open_button = make_button("▭  Открыть папку", "secondaryButton")
        open_button.clicked.connect(lambda: open_in_file_manager(BACKUP_DIR))
        layout.addWidget(open_button)

        version = QLabel(f"{APP_NAME} {APP_VERSION}")
        version.setObjectName("version")
        layout.addWidget(version)
        return sidebar

    def _build_content(self) -> QWidget:
        content = QFrame()
        content.setObjectName("content")
        outer = QVBoxLayout(content)
        outer.setContentsMargins(34, 44, 34, 34)
        outer.setSpacing(22)

        header = QHBoxLayout()
        self.page_icon = QLabel("▤")
        self.page_icon.setObjectName("pageIcon")
        self.page_title = QLabel("Все бэкапы")
        self.page_title.setObjectName("pageTitle")
        refresh = make_button("↻  Обновить", "secondaryButton")
        refresh.clicked.connect(self.refresh_all)

        header.addWidget(self.page_icon)
        header.addWidget(self.page_title)
        header.addStretch(1)
        header.addWidget(refresh)
        outer.addLayout(header)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.dashboard_page = self._build_dashboard()
        self.create_page = self._build_create_page()
        self.restore_page = self._build_restore_page()
        self.logs_page = self._build_logs_page()
        self.stack.addWidget(self.dashboard_page)
        self.stack.addWidget(self.create_page)
        self.stack.addWidget(self.restore_page)
        self.stack.addWidget(self.logs_page)
        return content

    def _build_dashboard(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(20)
        layout.setVerticalSpacing(24)
        layout.setColumnStretch(0, 1)
        layout.setColumnMinimumWidth(1, 340)
        layout.setRowStretch(0, 3)
        layout.setRowStretch(1, 2)

        table_panel = panel()
        table_panel.setMinimumHeight(390)
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(30, 26, 30, 22)
        table_layout.setSpacing(16)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["№", "Имя файла", "Размер", "Дата создания"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setMinimumHeight(290)
        self.table.cellClicked.connect(self._select_row)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table_layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Всего бэкапов:"))
        self.total_label = QLabel("0")
        self.total_label.setObjectName("blueText")
        bottom.addWidget(self.total_label)
        bottom.addStretch(1)
        self.updated_label = QLabel("")
        self.updated_label.setObjectName("muted")
        bottom.addWidget(self.updated_label)
        table_layout.addLayout(bottom)
        layout.addWidget(table_panel, 0, 0)

        logs_panel = panel()
        logs_layout = QVBoxLayout(logs_panel)
        logs_layout.setContentsMargins(30, 20, 30, 20)
        logs_header = QHBoxLayout()
        log_title = QLabel("Последние логи")
        log_title.setObjectName("panelTitle")
        open_logs = make_button("▱  Открыть логи", "smallButton")
        open_logs.clicked.connect(lambda: self.show_page("logs"))
        logs_header.addWidget(log_title)
        logs_header.addStretch(1)
        logs_header.addWidget(open_logs)
        logs_layout.addLayout(logs_header)
        self.recent_logs = QTextEdit()
        self.recent_logs.setReadOnly(True)
        self.recent_logs.setFixedHeight(104)
        logs_layout.addWidget(self.recent_logs)
        layout.addWidget(logs_panel, 1, 0)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(20)

        actions = panel()
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(28, 28, 28, 28)
        actions_layout.setSpacing(10)
        title = QLabel("ⓘ  Быстрые действия")
        title.setObjectName("panelTitle")
        create = make_button("+  Создать бэкап", "quickPrimaryButton")
        create.clicked.connect(self.make_backup)
        restore = make_button("↻  Восстановить", "quickOrangeButton")
        restore.clicked.connect(self.restore_selected_or_latest)
        delete = make_button("Удалить выбранный", "quickDangerButton")
        delete.clicked.connect(self.delete_selected)
        for button in (create, restore, delete):
            button.setFixedHeight(64)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        actions_layout.addWidget(title)
        actions_layout.addSpacing(10)
        actions_layout.addWidget(create)
        actions_layout.addWidget(restore)
        actions_layout.addWidget(delete)
        right_layout.addWidget(actions)

        last = panel()
        last_layout = QVBoxLayout(last)
        last_layout.setContentsMargins(28, 28, 28, 28)
        last_title = QLabel("О последнем бэкапе")
        last_title.setObjectName("panelTitle")
        self.last_info = QLabel("")
        self.last_info.setObjectName("infoText")
        self.last_info.setWordWrap(True)
        self.last_info.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        last_layout.addWidget(last_title)
        last_layout.addSpacing(12)
        last_layout.addWidget(self.last_info, 1)
        right_layout.addWidget(last, 1)
        layout.addWidget(right, 0, 1, 2, 1)
        return page

    def _build_create_page(self) -> QWidget:
        page = panel()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 40, 48, 48)
        layout.setSpacing(22)
        layout.addWidget(title_label("Создание бэкапа"), alignment=Qt.AlignmentFlag.AlignHCenter)
        self.source_label = drop_label("Папка или файл не выбраны\nМожно перетащить файл или папку в окно")
        layout.addWidget(self.source_label)

        controls = QHBoxLayout()
        controls.setSpacing(14)
        button_group = QHBoxLayout()
        button_group.setSpacing(12)
        choose_folder = make_button("Выбрать папку", "secondaryButton")
        choose_folder.clicked.connect(self.choose_source_folder)
        choose_file = make_button("Выбрать файл", "secondaryButton")
        choose_file.clicked.connect(self.choose_source_file)
        choose_folder.setFixedWidth(180)
        choose_file.setFixedWidth(180)
        button_group.addWidget(choose_folder)
        button_group.addWidget(choose_file)

        self.source_summary = QLabel("Источник не выбран")
        self.source_summary.setObjectName("sourceSummary")
        self.source_summary.setWordWrap(True)

        controls.addLayout(button_group)
        controls.addWidget(self.source_summary, 1)
        layout.addLayout(controls)

        create = make_button("+  Создать бэкап", "primaryButton")
        create.clicked.connect(self.make_backup)
        layout.addWidget(create, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        return page

    def _build_restore_page(self) -> QWidget:
        page = panel()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 40, 48, 48)
        layout.setSpacing(18)
        layout.addWidget(title_label("Восстановление"), alignment=Qt.AlignmentFlag.AlignHCenter)
        self.restore_label = drop_label(f"Папка восстановления:\n{self.restore_target}")
        layout.addWidget(self.restore_label)

        controls = QHBoxLayout()
        controls.setSpacing(18)
        choose_target = make_button("Выбрать папку восстановления", "secondaryButton")
        choose_target.setFixedWidth(320)
        choose_target.clicked.connect(self.choose_restore_target)
        restore = make_button("↻  Восстановить выбранный или последний", "orangeButton")
        restore.setFixedWidth(430)
        restore.clicked.connect(self.restore_selected_or_latest)
        controls.addWidget(choose_target, alignment=Qt.AlignmentFlag.AlignLeft)
        controls.addStretch(1)
        controls.addWidget(restore, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(controls)

        list_title = QLabel("Выберите бэкап для восстановления")
        list_title.setObjectName("panelTitle")
        layout.addWidget(list_title)

        self.restore_table = QTableWidget(0, 4)
        self.restore_table.setObjectName("restoreTable")
        self.restore_table.setHorizontalHeaderLabels(["№", "Имя файла", "Размер", "Дата создания"])
        self.restore_table.verticalHeader().setVisible(False)
        self.restore_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.restore_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.restore_table.setShowGrid(False)
        self.restore_table.cellClicked.connect(self._select_restore_row)
        restore_header = self.restore_table.horizontalHeader()
        restore_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        restore_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        restore_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        restore_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.restore_table, 1)
        return page

    def _build_logs_page(self) -> QWidget:
        page = panel()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 24, 30, 30)
        layout.setSpacing(16)

        top = QHBoxLayout()
        heading = QLabel("Журнал действий")
        heading.setObjectName("panelTitle")
        open_folder = make_button("▭  Открыть папку", "smallButton")
        open_folder.clicked.connect(lambda: open_in_file_manager(LOG_FILE.parent))
        clear = make_button("Очистить", "dangerButton")
        clear.clicked.connect(self.clear_logs)
        top.addWidget(heading)
        top.addStretch(1)
        top.addWidget(open_folder)
        top.addWidget(clear)
        layout.addLayout(top)

        self.full_logs = QTextEdit()
        self.full_logs.setObjectName("fullLogs")
        self.full_logs.setReadOnly(True)
        layout.addWidget(self.full_logs, 1)
        return page

    def show_page(self, page: str) -> None:
        titles = {
            "home": ("▤", "Все бэкапы", 0),
            "create": ("+", "Создание бэкапа", 1),
            "restore": ("↻", "Восстановление", 2),
            "logs": ("▣", "Логи", 3),
        }
        icon, title, index = titles[page]
        self.page_icon.setText(icon)
        self.page_title.setText(title)
        self.stack.setCurrentIndex(index)
        for key, button in self.nav_buttons.items():
            button.setChecked(key == page)
        self.refresh_all()

    def refresh_all(self) -> None:
        self.backups = list_backups()
        if self.selected_backup and not self.selected_backup.path.exists():
            self.selected_backup = None
        if not self.selected_backup and self.backups:
            self.selected_backup = self.backups[-1]
        self._render_table()
        self._render_restore_table()
        self._render_last_info()
        self._render_logs()

    def _render_table(self) -> None:
        self.table.setRowCount(len(self.backups))
        for row, backup in enumerate(self.backups):
            values = [str(row + 1), backup.name, backup.size_label, backup.date_label]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setForeground(QColor("#f5f7fb"))
                if column == 1:
                    item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                item.setData(Qt.ItemDataRole.UserRole, str(backup.path))
                self.table.setItem(row, column, item)

            self.table.setRowHeight(row, 38)

            if self.selected_backup and backup.path == self.selected_backup.path:
                self.table.selectRow(row)

        self.total_label.setText(str(len(self.backups)))
        self.updated_label.setText(f"↻  Последнее обновление: {datetime.now().strftime('%H:%M:%S')}")

    def _render_restore_table(self) -> None:
        self.restore_table.setRowCount(len(self.backups))
        for row, backup in enumerate(self.backups):
            values = [str(row + 1), backup.name, backup.size_label, backup.date_label]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setForeground(QColor("#f5f7fb"))
                if column == 1:
                    item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                item.setData(Qt.ItemDataRole.UserRole, str(backup.path))
                self.restore_table.setItem(row, column, item)
            self.restore_table.setRowHeight(row, 40)

            if self.selected_backup and backup.path == self.selected_backup.path:
                self.restore_table.selectRow(row)

    def _render_last_info(self) -> None:
        backup = self.backups[-1] if self.backups else None
        if not backup:
            self.last_info.setText("Файл:\nнет данных\n\nРазмер:\n-\n\nДата:\n-")
            return
        self.last_info.setText(f"Файл:\n{backup.name}\n\nРазмер:\n{backup.size_label}\n\nДата:\n{backup.date_label}")

    def _render_logs(self) -> None:
        lines = read_logs()[-500:]
        self.recent_logs.setPlainText("\n".join(lines[-6:]))
        self.full_logs.setPlainText("\n".join(lines))
        self.full_logs.moveCursor(self.full_logs.textCursor().MoveOperation.End)

    def _select_row(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.backups):
            self.selected_backup = self.backups[row]
            self.table.selectRow(row)
            self.restore_table.selectRow(row)

    def _select_restore_row(self, row: int, _column: int) -> None:
        if 0 <= row < len(self.backups):
            self.selected_backup = self.backups[row]
            self.restore_table.selectRow(row)
            self.table.selectRow(row)

    def choose_source_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для бэкапа")
        if folder:
            self.source_path = Path(folder)
            self._update_source_path()

    def choose_source_file(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, "Выберите файл для бэкапа")
        if file:
            self.source_path = Path(file)
            self._update_source_path()

    def choose_restore_target(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку восстановления")
        if folder:
            self.restore_target = Path(folder)
            self.restore_label.setText(f"Папка восстановления:\n{self.restore_target}")

    def make_backup(self) -> None:
        if not self.source_path:
            self.show_page("create")
            show_message(self, "Сначала выберите папку или файл для бэкапа.", "warning")
            return
        try:
            backup = create_zip_backup(self.source_path)
            self.selected_backup = backup
            write_log("УСПЕХ", f"Бэкап успешно создан: {backup.name}")
            self.refresh_all()
            show_message(self, "Бэкап создан.", "info")
        except Exception as error:
            write_log("ОШИБКА", f"Не удалось создать бэкап: {error}")
            self.refresh_all()
            show_message(self, str(error), "error")

    def restore_selected_or_latest(self) -> None:
        backup = self.selected_backup or (self.backups[-1] if self.backups else None)
        if not backup:
            show_message(self, "Нет доступных бэкапов для восстановления.", "warning")
            return
        if not ask_question(self, f"Восстановить {backup.name} в папку:\n{self.restore_target}?"):
            return
        try:
            safe_extract_zip(backup.path, self.restore_target)
            write_log("УСПЕХ", f"Бэкап восстановлен: {backup.name} -> {self.restore_target}")
            self.refresh_all()
            show_message(self, "Восстановление завершено.", "info")
        except Exception as error:
            write_log("ОШИБКА", f"Не удалось восстановить {backup.name}: {error}")
            self.refresh_all()
            show_message(self, str(error), "error")

    def delete_selected(self) -> None:
        if not self.selected_backup:
            show_message(self, "Выберите бэкап в таблице.", "warning")
            return
        self.delete_backup(self.selected_backup)

    def delete_backup(self, backup: BackupInfo) -> None:
        if not ask_question(
            self,
            f"Удалить бэкап без возможности восстановления?\n\n{backup.name}",
            confirm_text="Удалить",
            cancel_text="Отмена",
            confirm_style="confirmDeleteButton",
            cancel_style="confirmCancelButton",
        ):
            return
        try:
            backup.path.unlink()
            write_log("УСПЕХ", f"Бэкап удалён: {backup.name}")
            self.selected_backup = None
            self.refresh_all()
        except Exception as error:
            write_log("ОШИБКА", f"Не удалось удалить {backup.name}: {error}")
            self.refresh_all()
            show_message(self, str(error), "error")

    def clear_logs(self) -> None:
        if not ask_question(self, "Очистить журнал действий?"):
            return
        LOG_FILE.write_text("", encoding="utf-8")
        write_log("ИНФО", "Журнал очищен")
        self.refresh_all()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        if path.exists():
            self.source_path = path
            self._update_source_path()
            write_log("ИНФО", f"Выбран источник перетаскиванием: {path}")
            self.show_page("create")

    def _update_source_path(self) -> None:
        if not self.source_path:
            text = "Папка или файл не выбраны\nМожно перетащить файл или папку в окно"
            summary = "Источник не выбран"
        else:
            kind = "Файл" if self.source_path.is_file() else "Папка"
            text = f"{kind} выбран(а)\n{self.source_path}"
            summary = str(self.source_path)
        self.source_label.setText(text)
        self.source_summary.setText(summary)


def make_button(text: str, object_name: str) -> ImpactButton:
    button = ImpactButton(text)
    button.setObjectName(object_name)
    return button


def panel() -> QFrame:
    frame = QFrame()
    frame.setObjectName("panel")
    frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return frame


def title_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("formTitle")
    return label


def drop_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("dropLabel")
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label


STYLES = """
#root, #content {
    background: #111418;
    color: #f5f7fb;
    font-family: "Segoe UI";
}
#sidebar {
    background: #11161c;
    border-right: 1px solid #303640;
}
#brand {
    color: #f5f7fb;
    font-size: 24px;
    font-weight: 800;
}
#logoMark {
    border: none;
    background: transparent;
}
#pageIcon {
    color: #1e90ff;
    font-size: 30px;
    font-weight: 800;
}
#pageTitle {
    color: #f5f7fb;
    font-size: 30px;
    font-weight: 800;
}
#panel {
    background: #181d23;
    border: 1px solid #343a43;
    border-radius: 12px;
}
#panelTitle {
    color: #f5f7fb;
    font-size: 19px;
    font-weight: 800;
}
#formTitle {
    color: #f5f7fb;
    font-size: 24px;
    font-weight: 800;
}
#dropLabel {
    background: #11151a;
    color: #aeb6c2;
    border: 1px solid #343a43;
    border-radius: 12px;
    min-height: 130px;
    padding: 24px;
    font-size: 15px;
}
#sourceSummary {
    background: #11151a;
    color: #d9dee7;
    border: 1px solid #343a43;
    border-radius: 10px;
    min-height: 50px;
    padding: 0 18px;
    font-size: 13px;
}
#smallMuted, #muted, #version {
    color: #aeb6c2;
    font-size: 12px;
}
#blueText {
    color: #1e90ff;
    font-size: 16px;
    font-weight: 800;
}
#infoText {
    color: #f5f7fb;
    font-size: 14px;
}
#line {
    background: #303640;
}
QLabel {
    color: #f5f7fb;
}
QPushButton {
    min-height: 42px;
    padding: 0 18px;
    border-radius: 10px;
    color: #f5f7fb;
    font-size: 14px;
    font-weight: 700;
    background: #20242b;
    border: 1px solid #343a43;
    text-align: center;
}
QPushButton:hover {
    background: #2a3039;
}
QPushButton:pressed {
    padding-top: 2px;
    padding-left: 2px;
    border-color: #6d7b8e;
}
#navButton {
    min-height: 58px;
    max-height: 58px;
    padding-left: 22px;
    padding-right: 18px;
    text-align: left;
    font-size: 16px;
    border-radius: 10px;
}
#navButton:checked {
    background: #1e90ff;
    border-color: #1e90ff;
}
#primaryButton {
    background: #1e90ff;
    border-color: #1e90ff;
    min-width: 260px;
    min-height: 56px;
    font-size: 16px;
}
#primaryButton:hover {
    background: #0f68d8;
}
#primaryButton:pressed {
    background: #0b55b5;
}
#orangeButton {
    background: #ff8a16;
    border-color: #ff8a16;
    min-width: 260px;
    min-height: 56px;
    font-size: 16px;
}
#orangeButton:hover {
    background: #d66b00;
}
#orangeButton:pressed {
    background: #ad5200;
}
#dangerButton {
    background: #382020;
    border-color: #5a2d2d;
}
#dangerButton:hover {
    background: #4a2525;
}
#dangerButton:pressed {
    background: #612b2b;
}
#quickPrimaryButton, #quickOrangeButton, #quickDangerButton {
    min-height: 64px;
    max-height: 64px;
    font-size: 16px;
    text-align: center;
}
#quickPrimaryButton {
    background: #1e90ff;
    border-color: #1e90ff;
}
#quickPrimaryButton:hover {
    background: #0f68d8;
}
#quickPrimaryButton:pressed {
    background: #0b55b5;
}
#quickOrangeButton {
    background: #ff8a16;
    border-color: #ff8a16;
}
#quickOrangeButton:hover {
    background: #d66b00;
}
#quickOrangeButton:pressed {
    background: #ad5200;
}
#quickDangerButton {
    background: #382020;
    border-color: #5a2d2d;
}
#quickDangerButton:hover {
    background: #4a2525;
}
#quickDangerButton:pressed {
    background: #612b2b;
}
#confirmDeleteButton {
    background: #d83a3a;
    border-color: #ef5350;
    min-width: 170px;
    min-height: 54px;
    font-size: 15px;
}
#confirmDeleteButton:hover {
    background: #b92f2f;
}
#confirmDeleteButton:pressed {
    background: #922525;
}
#confirmCancelButton {
    background: #1e90ff;
    border-color: #1e90ff;
    min-width: 170px;
    min-height: 54px;
    font-size: 15px;
}
#confirmCancelButton:hover {
    background: #0f68d8;
}
#confirmCancelButton:pressed {
    background: #0b55b5;
}
#smallButton {
    min-height: 34px;
    font-size: 13px;
}
QTableWidget {
    background: #11151a;
    color: #f5f7fb;
    border: 1px solid #2c323b;
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: #1d2229;
    selection-color: #f5f7fb;
    font-size: 13px;
}
QHeaderView::section {
    background: #20242b;
    color: #f5f7fb;
    border: none;
    padding: 12px;
    font-weight: 800;
}
QTableWidget::item {
    padding: 10px;
    border-bottom: 1px solid #20252c;
}
QTextEdit {
    background: #11151a;
    color: #d9dee7;
    border: 1px solid #2c323b;
    border-radius: 6px;
    font-family: Consolas;
    font-size: 12px;
}
#fullLogs {
    font-size: 13px;
}
#appDialog {
    background: #181d23;
}
#dialogText {
    color: #f5f7fb;
    font-size: 15px;
}
#dialogIcon_info, #dialogIcon_question {
    background: #1e90ff;
    color: white;
    border-radius: 21px;
    font-size: 24px;
    font-weight: 800;
}
#dialogIcon_warning {
    background: #ff8a16;
    color: white;
    border-radius: 21px;
    font-size: 24px;
    font-weight: 800;
}
#dialogIcon_error {
    background: #ef5350;
    color: white;
    border-radius: 21px;
    font-size: 24px;
    font-weight: 800;
}
"""


def main() -> None:
    ensure_dirs()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = XQuickWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
