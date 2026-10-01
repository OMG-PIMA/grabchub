import sys
import os
import json
import base64
import sqlite3
import re
import shutil
import random
from PIL import Image

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
    QPushButton, QTextBrowser, QLabel, QFileDialog, QStyle, QLineEdit, 
    QProgressBar, QDialog, QFormLayout, QDialogButtonBox, QCheckBox,
    QPlainTextEdit, QSizePolicy, QSplitter, QMessageBox
)
from PyQt6.QtGui import QPixmap, QKeyEvent, QFontMetrics, QTextOption
from PyQt6.QtCore import Qt, QThread, pyqtSignal

# ----------------- CUSTOM MULTI-EXPAND ACCORDION -----------------
class CollapsibleBox(QWidget):
    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self.base_title = title
        
        self.toggle_button = QPushButton(f"▼  {title}")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(True) 
        self.toggle_button.setStyleSheet("""
            QPushButton {
                background: #333;
                color: #ddd;
                font-weight: bold;
                text-align: left;
                padding: 8px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:checked {
                background: #555;
                color: white;
            }
        """)
        
        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(0, 5, 0, 5) 
        
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.toggle_button)
        main_layout.addWidget(self.content_area)
        
        self.toggle_button.clicked.connect(self.on_toggle)
        
    def on_toggle(self, checked):
        self.content_area.setVisible(checked)
        self.toggle_button.setText(f"▼  {self.base_title}" if checked else f"▶  {self.base_title}")
        
    def setWidget(self, widget):
        self.content_layout.addWidget(widget)


# ----------------- WORKER THREAD FOR DATABASE INDEXING -----------------
class DatabaseWorker(QThread):
    progress_update = pyqtSignal(int, int) 
    finished = pyqtSignal(list)            

    def __init__(self, directory):
        super().__init__()
        self.directory = directory

    def run(self):
        png_files = [f for f in os.listdir(self.directory) if f.lower().endswith('.png')]
        total_files = len(png_files)
        
        if total_files == 0:
            self.finished.emit([])
            return

        db_path = os.path.join(self.directory, "cards_cache.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS character_cards (
                filename TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                tags TEXT,
                greeting TEXT,
                favorite INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

        for index, filename in enumerate(png_files):
            self.progress_update.emit(index + 1, total_files)
            
            cursor.execute("SELECT 1 FROM character_cards WHERE filename = ?", (filename,))
            if cursor.fetchone():
                continue

            full_path = os.path.join(self.directory, filename)
            try:
                img = Image.open(full_path)
                metadata = img.text if hasattr(img, 'text') else img.info
                
                if 'chara' in metadata:
                    raw_b64 = metadata['chara']
                    raw_b64 += "=" * ((4 - len(raw_b64) % 4) % 4)
                    decoded_bytes = base64.b64decode(raw_b64)
                    json_data = json.loads(decoded_bytes.decode('utf-8'))
                    char_info = json_data.get("data", json_data)
                    
                    name = char_info.get("name", filename)
                    description = char_info.get("description", "")
                    
                    tags_list = char_info.get("topics", char_info.get("tags", []))
                    tags = ", ".join([str(t).strip() for t in tags_list if str(t).strip()]) if isinstance(tags_list, list) else ""
                    
                    main_greeting = char_info.get("first_mes", char_info.get("greeting", ""))
                    alt_greetings = char_info.get("alternate_greetings", [])
                    
                    greetings_list = [main_greeting] if main_greeting.strip() else []
                    if isinstance(alt_greetings, list):
                        greetings_list.extend([g for g in alt_greetings if isinstance(g, str) and g.strip()])
                        
                    greeting = "\n\n========== ALTERNATE GREETING ==========\n\n".join(greetings_list)
                    
                    cursor.execute(
                        "INSERT OR REPLACE INTO character_cards (filename, name, description, tags, greeting, favorite) VALUES (?, ?, ?, ?, ?, 0)",
                        (filename, name, description, tags, greeting)
                    )
            except Exception:
                cursor.execute(
                    "INSERT OR REPLACE INTO character_cards (filename, name, description, tags, greeting, favorite) VALUES (?, ?, ?, ?, ?, 0)",
                    (filename, filename, "Unreadable metadata structure.", "", "")
                )
            
            if index % 50 == 0:
                conn.commit()

        conn.commit()
        conn.close()
        
        png_files.sort()
        self.finished.emit(png_files)


# ----------------- ADVANCED SEARCH MODAL DIALOG -----------------
class AdvancedSearchDialog(QDialog):
    def __init__(self, parent=None, initial_desc="", initial_tags="", initial_greet="", initial_fav=False):
        super().__init__(parent)
        self.setWindowTitle("Advanced Search Configuration")
        self.setModal(True)
        self.resize(500, 350) 
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15) 
        layout.setSpacing(10)
        
        form_layout = QFormLayout()
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(8)
        
        self.te_desc = QPlainTextEdit(initial_desc)
        self.te_desc.setPlaceholderText('e.g. "magic sword" elf friendly...')
        
        self.te_tags = QPlainTextEdit(initial_tags)
        self.te_tags.setPlaceholderText('e.g. "high fantasy" magic...')
        
        self.te_greet = QPlainTextEdit(initial_greet)
        self.te_greet.setPlaceholderText('e.g. "hello traveler" tavern...')
        
        font_metrics = self.te_desc.fontMetrics()
        line_height = font_metrics.lineSpacing()
        target_height = (line_height * 3) + 12 
        
        self.te_desc.setFixedHeight(target_height)
        self.te_tags.setFixedHeight(target_height)
        self.te_greet.setFixedHeight(target_height)
        
        form_layout.addRow("Description Filter:", self.te_desc)
        form_layout.addRow("Tags / Topics Filter:", self.te_tags)
        form_layout.addRow("Greeting Filter:", self.te_greet)
        
        self.chk_fav = QCheckBox("Show Only Favorites")
        self.chk_fav.setChecked(initial_fav)
        form_layout.addRow("", self.chk_fav)
        
        layout.addLayout(form_layout)
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        
    def get_values(self):
        desc_text = self.te_desc.toPlainText().replace('\n', ' ').strip()
        tags_text = self.te_tags.toPlainText().replace('\n', ' ').strip()
        greet_text = self.te_greet.toPlainText().replace('\n', ' ').strip()
        return desc_text, tags_text, greet_text, self.chk_fav.isChecked()


# ----------------- MAIN APPLICATION WINDOW -----------------
class CardViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Character Card Viewer")
        self.resize(1100, 800)
        
        self.all_image_files = []      
        self.filtered_image_files = [] 
        self.current_index = -1
        self.current_dir = ""

        self.adv_desc = ""
        self.adv_tags = ""
        self.adv_greet = ""
        self.adv_fav_only = False
        self.is_advanced_search_active = False
        
        self.active_highlight_terms = []

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # ----------------- LEFT SIDE (Master View) -----------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        self.btn_open = QPushButton("Open Folder...")
        self.btn_open.clicked.connect(self.open_directory)
        left_layout.addWidget(self.btn_open)

        nsfw_export_layout = QHBoxLayout()
        
        self.chk_hide_images = QCheckBox("Hide All Images")
        self.chk_hide_images.setChecked(True)
        self.chk_hide_images.stateChanged.connect(self.load_card)
        nsfw_export_layout.addWidget(self.chk_hide_images)

        self.btn_export_favs = QPushButton("Export Favs...")
        self.btn_export_favs.setToolTip("Copy all favorited PNGs to a new directory")
        self.btn_export_favs.clicked.connect(self.export_favorites)
        self.btn_export_favs.setEnabled(False)
        nsfw_export_layout.addWidget(self.btn_export_favs)

        # NEW: Randomize Button
        self.btn_randomize = QPushButton("Randomize")
        self.btn_randomize.setToolTip("Shuffle the display order of the current cards")
        self.btn_randomize.clicked.connect(self.randomize_order)
        self.btn_randomize.setEnabled(False)
        nsfw_export_layout.addWidget(self.btn_randomize)

        left_layout.addLayout(nsfw_export_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        left_layout.addWidget(self.progress_bar)

        self.lbl_image = QLabel("No Folder Loaded")
        self.lbl_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_image.setStyleSheet("border: 2px dashed #888; background: #222; color: #aaa;")
        
        self.lbl_image.setMinimumSize(300, 400)
        self.lbl_image.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            
        img_layout = QVBoxLayout(self.lbl_image)
        img_layout.setContentsMargins(10, 10, 10, 10)
        
        top_overlay_row = QHBoxLayout()
        top_overlay_row.addStretch() 
        
        self.btn_favorite = QPushButton("☆")
        self.btn_favorite.setFixedSize(45, 45)
        self.btn_favorite.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_favorite.clicked.connect(self.toggle_favorite)
        self.btn_favorite.setVisible(False)
        
        top_overlay_row.addWidget(self.btn_favorite)
        img_layout.addLayout(top_overlay_row)
        img_layout.addStretch() 

        left_layout.addWidget(self.lbl_image)

        nav_widget = QWidget()
        nav_layout = QHBoxLayout(nav_widget)
        
        self.btn_prev = QPushButton()
        self.btn_prev.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowLeft))
        self.btn_prev.clicked.connect(self.prev_card)
        self.btn_prev.setEnabled(False)
        
        self.lbl_counter = QLabel("0 of 0")
        self.lbl_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_counter.setStyleSheet("font-weight: bold; color: #666;")
        
        self.btn_next = QPushButton()
        self.btn_next.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowRight))
        self.btn_next.clicked.connect(self.next_card)
        self.btn_next.setEnabled(False)
        
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.lbl_counter)
        nav_layout.addWidget(self.btn_next)
        left_layout.addWidget(nav_widget)

        # ----------------- RIGHT SIDE (Detail View) -----------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.lbl_title = QLabel("Character Details")
        self.lbl_title.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        right_layout.addWidget(self.lbl_title)

        self.lbl_filename = QLabel("")
        self.lbl_filename.setStyleSheet("color: #888; font-size: 12px; font-family: monospace; margin-bottom: 4px;")
        right_layout.addWidget(self.lbl_filename)

        self.txt_detail = QTextBrowser()
        self.txt_detail.setPlaceholderText("Select a folder containing character cards.")
        self.txt_detail.setStyleSheet("font-size: 14px;")

        self.txt_tags = QTextBrowser()
        self.txt_tags.setPlaceholderText("Tags will appear here.")
        self.txt_tags.setStyleSheet("font-size: 13px;") 

        self.txt_greeting = QTextBrowser()
        self.txt_greeting.setPlaceholderText("Greetings will appear here.")
        self.txt_greeting.setStyleSheet("font-size: 14px;")

        for text_browser in (self.txt_detail, self.txt_tags, self.txt_greeting):
            text_browser.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)

        self.accordion = QSplitter(Qt.Orientation.Vertical)
        self.accordion.setChildrenCollapsible(False) 
        self.accordion.setStyleSheet("""
            QSplitter::handle {
                background-color: #444;
                height: 4px;
                margin: 4px 0px;
                border-radius: 2px;
            }
        """)
        
        self.box_desc = CollapsibleBox("Description")
        self.box_desc.setWidget(self.txt_detail)
        
        self.box_greet = CollapsibleBox("Greeting / First Message")
        self.box_greet.setWidget(self.txt_greeting)
        
        self.box_tags = CollapsibleBox("Tags / Topics")
        self.box_tags.setWidget(self.txt_tags)
        
        self.accordion.addWidget(self.box_desc)
        self.accordion.addWidget(self.box_greet)
        self.accordion.addWidget(self.box_tags)
        
        right_layout.addWidget(self.accordion, stretch=4)

        lbl_search_header = QLabel("Search System (Filters Name, Description, Tags, and Greetings):")
        lbl_search_header.setStyleSheet("font-weight: bold; color: #555; margin-top: 10px;")
        right_layout.addWidget(lbl_search_header)

        search_layout = QHBoxLayout()
        
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Type terms and press Enter to search...")
        self.search_box.setClearButtonEnabled(True)
        
        self.search_box.returnPressed.connect(lambda: self.execute_search(self.search_box.text()))
        self.search_box.textChanged.connect(lambda text: self.execute_search("") if text == "" else None)
        
        self.search_box.setEnabled(False)
        search_layout.addWidget(self.search_box)

        self.btn_clear_search = QPushButton("X")
        self.btn_clear_search.setFixedWidth(30)
        self.btn_clear_search.setToolTip("Clear Search")
        self.btn_clear_search.clicked.connect(self.clear_all_searches)
        self.btn_clear_search.setEnabled(False)
        search_layout.addWidget(self.btn_clear_search)

        self.btn_adv_search = QPushButton("...")
        self.btn_adv_search.setFixedWidth(35)
        self.btn_adv_search.setToolTip("Open Advanced Multi-Field Parameters Engine")
        self.btn_adv_search.clicked.connect(self.open_advanced_search)
        self.btn_adv_search.setEnabled(False)
        search_layout.addWidget(self.btn_adv_search)

        right_layout.addLayout(search_layout)

        main_layout.addWidget(left_widget, stretch=1)
        main_layout.addWidget(right_widget, stretch=2)

    def trigger_filter_update(self):
        if self.is_advanced_search_active:
            self.execute_advanced_search()
        else:
            self.execute_search(self.search_box.text())

    def update_favorite_icon_style(self, is_favorite):
        if is_favorite:
            self.btn_favorite.setText("★")
            self.btn_favorite.setStyleSheet("""
                QPushButton { background-color: rgba(0, 0, 0, 150); color: gold; font-size: 28px; border-radius: 22px; padding-bottom: 4px; }
            """)
        else:
            self.btn_favorite.setText("☆")
            self.btn_favorite.setStyleSheet("""
                QPushButton { background-color: rgba(0, 0, 0, 150); color: white; font-size: 28px; border-radius: 22px; padding-bottom: 4px; }
                QPushButton:hover { color: gold; }
            """)

    def toggle_favorite(self):
        if self.current_index == -1 or not self.filtered_image_files:
            return
            
        filename = self.filtered_image_files[self.current_index]
        db_path = os.path.join(self.current_dir, "cards_cache.db")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT favorite FROM character_cards WHERE filename = ?", (filename,))
        row = cursor.fetchone()
        
        if row is not None:
            new_fav_state = 0 if row[0] == 1 else 1
            cursor.execute("UPDATE character_cards SET favorite = ? WHERE filename = ?", (new_fav_state, filename))
            conn.commit()
            self.update_favorite_icon_style(new_fav_state)
            
        conn.close()

    def export_favorites(self):
        if not self.current_dir or not self.all_image_files:
            return

        db_path = os.path.join(self.current_dir, "cards_cache.db")
        if not os.path.exists(db_path):
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM character_cards WHERE favorite = 1")
        fav_files = [row[0] for row in cursor.fetchall()]
        conn.close()

        if not fav_files:
            QMessageBox.information(self, "Export Favorites", "No favorites found to export. Star some cards first!")
            return

        dest_dir = QFileDialog.getExistingDirectory(self, "Select Destination Directory for Favorites")
        if not dest_dir:
            return

        success_count = 0
        for filename in fav_files:
            src_path = os.path.join(self.current_dir, filename)
            dest_path = os.path.join(dest_dir, filename)
            try:
                if os.path.exists(src_path):
                    shutil.copy2(src_path, dest_path)
                    success_count += 1
            except Exception as e:
                print(f"Failed to copy {filename}: {e}")

        QMessageBox.information(self, "Export Complete", f"Successfully copied {success_count} of {len(fav_files)} favorited PNGs.")

    def randomize_order(self):
        if not self.filtered_image_files:
            return
        
        random.shuffle(self.filtered_image_files)
        self.current_index = 0
        self.update_ui_state()
        self.load_card()

    def parse_search_query(self, query_text):
        terms = []
        for match in re.finditer(r'"([^"]+)"|(\w+)', query_text):
            if match.group(1):
                terms.append(match.group(1).strip())
            elif match.group(2):
                terms.append(match.group(2).strip())
        return [t for t in terms if t]

    def apply_highlighting(self, text, terms):
        if not text:
            return ""
            
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        if not terms:
            return text.replace("\n", "<br>")

        escaped_terms = [re.escape(t) for t in terms if t.strip()]
        if not escaped_terms:
            return text.replace("\n", "<br>")
            
        escaped_terms.sort(key=len, reverse=True)
        pattern = re.compile(rf"(?<!\w)({'|'.join(escaped_terms)})(?!\w)", re.IGNORECASE)
        highlighted_text = pattern.sub(lambda m: f'<span style="color: red; font-weight: bold;">{m.group(0)}</span>', text)
        
        return highlighted_text.replace("\n", "<br>")

    def open_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Folder Containing PNGs")
        if not dir_path:
            return
            
        self.current_dir = dir_path
        self.btn_open.setEnabled(False)
        self.search_box.setEnabled(False)
        self.btn_clear_search.setEnabled(False)
        self.btn_adv_search.setEnabled(False)
        self.btn_export_favs.setEnabled(False)
        self.btn_randomize.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.lbl_image.setText("Preprocessing file metadata cache database storage layers...")

        self.worker = DatabaseWorker(dir_path)
        self.worker.progress_update.connect(self.update_indexing_progress)
        self.worker.finished.connect(self.on_indexing_finished)
        self.worker.start()

    def update_indexing_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"Caching: {current}/{total} cards")

    def on_indexing_finished(self, file_list):
        self.progress_bar.setVisible(False)
        self.btn_open.setEnabled(True)
        self.search_box.setEnabled(True)
        self.btn_clear_search.setEnabled(True)
        self.btn_adv_search.setEnabled(True)
        self.btn_export_favs.setEnabled(True)
        self.btn_randomize.setEnabled(True)
        
        self.reset_search_state()
        self.all_image_files = file_list
        
        self.trigger_filter_update()

    def open_advanced_search(self):
        dialog = AdvancedSearchDialog(self, self.adv_desc, self.adv_tags, self.adv_greet, self.adv_fav_only)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            desc_val, tags_val, greet_val, fav_val = dialog.get_values()
            
            if desc_val or tags_val or greet_val or fav_val:
                self.adv_desc = desc_val
                self.adv_tags = tags_val
                self.adv_greet = greet_val
                self.adv_fav_only = fav_val
                self.is_advanced_search_active = True
                
                # Build the dynamic summary string
                summary_parts = []
                if desc_val:
                    summary_parts.append(desc_val)
                if tags_val:
                    summary_parts.append(tags_val)
                if greet_val:
                    summary_parts.append(greet_val)
                if fav_val:
                    summary_parts.append("Favorites")
                    
                summary_str = " | ".join(summary_parts)
                display_text = f"<advanced {summary_str}>" if summary_str else "<advanced>"
                
                self.search_box.blockSignals(True)
                self.search_box.setText(display_text)
                self.search_box.setReadOnly(True)
                self.search_box.blockSignals(False)
                
                self.execute_advanced_search()
            else:
                self.clear_all_searches()

    def clear_all_searches(self):
        self.reset_search_state()
        self.trigger_filter_update()

    def reset_search_state(self):
        self.is_advanced_search_active = False
        self.adv_desc = ""
        self.adv_tags = ""
        self.adv_greet = ""
        self.adv_fav_only = False
        self.active_highlight_terms = [] 
        
        self.search_box.blockSignals(True)
        self.search_box.clear()
        self.search_box.setReadOnly(False)
        self.search_box.setPlaceholderText("Type terms and press Enter to search...")
        self.search_box.blockSignals(False)

    def execute_search(self, search_text):
        if not self.current_dir or not self.all_image_files:
            return

        if self.is_advanced_search_active:
            if search_text == "":
                self.reset_search_state()
            else:
                return

        search_text = search_text.strip()
        terms = self.parse_search_query(search_text)
        self.active_highlight_terms = terms
        
        db_path = os.path.join(self.current_dir, "cards_cache.db")
        conn = sqlite3.connect(db_path)
        conn.create_function("REGEXP", 2, lambda expr, item: item is not None and re.search(expr, str(item), re.IGNORECASE) is not None)
        cursor = conn.cursor()
        
        conditions = []
        params = []
        
        if terms:
            search_conds = []
            for term in terms:
                search_conds.append("(name REGEXP ? OR description REGEXP ? OR tags REGEXP ? OR greeting REGEXP ?)")
                query_val = rf"(?<!\w){re.escape(term)}(?!\w)"
                params.extend([query_val, query_val, query_val, query_val])
            conditions.append("(" + " AND ".join(search_conds) + ")")
            
        if not conditions:
            self.filtered_image_files = list(self.all_image_files)
        else:
            where_clause = " AND ".join(conditions)
            query = f"SELECT filename FROM character_cards WHERE {where_clause}"
            cursor.execute(query, params)
            
            matched_filenames = {row[0] for row in cursor.fetchall()}
            self.filtered_image_files = [f for f in self.all_image_files if f in matched_filenames]

        conn.close()

        if self.filtered_image_files:
            self.current_index = 0
        else:
            self.current_index = -1
            
        self.update_ui_state()
        self.load_card()

    def execute_advanced_search(self):
        if not self.current_dir or not self.all_image_files:
            return

        db_path = os.path.join(self.current_dir, "cards_cache.db")
        conn = sqlite3.connect(db_path)
        conn.create_function("REGEXP", 2, lambda expr, item: item is not None and re.search(expr, str(item), re.IGNORECASE) is not None)
        cursor = conn.cursor()
        
        conditions = []
        params = []
        self.active_highlight_terms = []
        
        if self.adv_desc:
            desc_terms = self.parse_search_query(self.adv_desc)
            for term in desc_terms:
                conditions.append("description REGEXP ?")
                params.append(rf"(?<!\w){re.escape(term)}(?!\w)")
                self.active_highlight_terms.append(term)
                
        if self.adv_tags:
            tag_terms = self.parse_search_query(self.adv_tags)
            for term in tag_terms:
                conditions.append("tags REGEXP ?")
                params.append(rf"(?<!\w){re.escape(term)}(?!\w)")
                self.active_highlight_terms.append(term)
                
        if self.adv_greet:
            greet_terms = self.parse_search_query(self.adv_greet)
            for term in greet_terms:
                conditions.append("greeting REGEXP ?")
                params.append(rf"(?<!\w){re.escape(term)}(?!\w)")
                self.active_highlight_terms.append(term)
                
        if self.adv_fav_only:
            conditions.append("favorite = 1")
                
        if not conditions:
            self.filtered_image_files = list(self.all_image_files)
        else:
            where_clause = " AND ".join(conditions)
            query = f"SELECT filename FROM character_cards WHERE {where_clause}"
            cursor.execute(query, params)
            
            matched_filenames = {row[0] for row in cursor.fetchall()}
            self.filtered_image_files = [f for f in self.all_image_files if f in matched_filenames]
            
        conn.close()
        
        if self.filtered_image_files:
            self.current_index = 0
        else:
            self.current_index = -1
            
        self.update_ui_state()
        self.load_card()

    def update_ui_state(self):
        if not self.filtered_image_files or self.current_index == -1:
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            return
        self.btn_prev.setEnabled(self.current_index > 0)
        self.btn_next.setEnabled(self.current_index < len(self.filtered_image_files) - 1)

    def load_card(self):
        if not self.filtered_image_files or self.current_index == -1:
            self.btn_favorite.setVisible(False)
            self.lbl_image.clear()
            self.lbl_image.setText("No matching results match active filter terms.")
            self.lbl_counter.setText(f"0 of {len(self.filtered_image_files)}")
            self.lbl_title.setText("No Results discovered")
            self.lbl_filename.clear()
            self.txt_detail.clear()
            self.txt_greeting.clear()
            self.txt_tags.clear()
            return

        filename = self.filtered_image_files[self.current_index]
        full_path = os.path.join(self.current_dir, filename)

        total_filtered = len(self.filtered_image_files)
        self.lbl_counter.setText(f"{self.current_index + 1} of {total_filtered}")

        metrics = QFontMetrics(self.lbl_filename.font())
        available_width = max(self.lbl_filename.width(), 450)
        elided_text = metrics.elidedText(filename, Qt.TextElideMode.ElideRight, available_width)
        
        self.lbl_filename.setText(elided_text)
        self.lbl_filename.setToolTip(filename)

        char_name, char_desc, char_tags, char_greet, char_fav = "", "", "", "", 0
        try:
            db_path = os.path.join(self.current_dir, "cards_cache.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name, description, tags, greeting, favorite FROM character_cards WHERE filename = ?", (filename,))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                char_name, char_desc, char_tags, char_greet, char_fav = row
                self.lbl_title.setText(char_name if char_name else "Unknown Character Object")
                self.lbl_title.setToolTip(char_name)
                
                if char_desc and char_desc.strip():
                    self.txt_detail.setHtml(self.apply_highlighting(char_desc, self.active_highlight_terms))
                else:
                    self.txt_detail.setPlainText("Description section is empty.")
                    
                if char_greet and char_greet.strip():
                    self.txt_greeting.setHtml(self.apply_highlighting(char_greet, self.active_highlight_terms))
                else:
                    self.txt_greeting.setPlainText("Greeting section is empty.")
                    
                if char_tags and char_tags.strip():
                    self.txt_tags.setHtml(self.apply_highlighting(char_tags, self.active_highlight_terms))
                else:
                    self.txt_tags.setPlainText("No topics attached to target metadata.")
            else:
                self.lbl_title.setText(filename)
                self.lbl_title.setToolTip(filename)
                self.txt_detail.setPlainText("Missing data parameters inside file indexing tables.")
                self.txt_greeting.setPlainText("N/A")
                self.txt_tags.setPlainText("N/A")
        except Exception as e:
            self.lbl_title.setText("Extraction Pipeline Fault")
            self.txt_detail.setPlainText(f"Failed query parameters updates:\n{str(e)}")
            self.txt_greeting.clear()
            self.txt_tags.clear()

        self.update_favorite_icon_style(char_fav)
        self.btn_favorite.setVisible(True)

        if self.chk_hide_images.isChecked():
            self.lbl_image.clear()
            self.lbl_image.setText("[ Image Hidden ]\n\nUncheck 'Hide All Images' above to view.")
        else:
            pixmap = QPixmap(full_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(
                    self.lbl_image.size(), 
                    Qt.AspectRatioMode.KeepAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                )
                self.lbl_image.setPixmap(scaled_pixmap)
            else:
                self.lbl_image.setText("Failed parsing operational local target graphical file assets.")

    def prev_card(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.update_ui_state()
            self.load_card()

    def next_card(self):
        if self.current_index < len(self.filtered_image_files) - 1:
            self.current_index += 1
            self.update_ui_state()
            self.load_card()

    def keyPressEvent(self, event: QKeyEvent):
        if self.current_index == -1:
            super().keyPressEvent(event)
            return
            
        if event.key() == Qt.Key.Key_Left:
            self.prev_card()
        elif event.key() == Qt.Key.Key_Right:
            self.next_card()
        else:
            super().keyPressEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = CardViewer()
    viewer.show()
    sys.exit(app.exec())