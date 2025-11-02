import sys
import PyPDF2
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QTextEdit, QProgressBar, QLabel, QPushButton, QMessageBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
import urllib.request
import urllib.parse
import json
import time
import re

class TranslatorThread(QThread):
    progress = pyqtSignal(int)
    status = pyqtSignal(str)
    result = pyqtSignal(str)
    error = pyqtSignal(str)
    
    def __init__(self, pdf_path):
        super().__init__()
        self.pdf_path = pdf_path
    
    def run(self):
        try:
            self.status.emit("PDFを読み込み中...")
            
            # PDFからテキストを抽出
            with open(self.pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                total_pages = len(pdf_reader.pages)
                
                self.status.emit(f"総ページ数: {total_pages}ページ")
                
                all_text = []
                
                for page_num in range(total_pages):
                    # ページを読み込み
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    
                    if text.strip():
                        all_text.append(f"\n{'='*50}\nページ {page_num + 1}\n{'='*50}\n")
                        
                        # 言語判定（簡易版）
                        is_english = self.is_english_text(text)
                        
                        if is_english:
                            self.status.emit(f"ページ {page_num + 1}/{total_pages} を翻訳中...")
                            
                            # テキストを整形してから翻訳
                            cleaned_text = self.clean_text(text)
                            translated_text = self.translate_text_mymemory(cleaned_text)
                            all_text.append(translated_text)
                        else:
                            self.status.emit(f"ページ {page_num + 1}/{total_pages} (日本語)")
                            all_text.append(text)
                    
                    # 進捗更新
                    progress_percent = int((page_num + 1) / total_pages * 100)
                    self.progress.emit(progress_percent)
                
                # 結果を返す
                final_text = "\n".join(all_text)
                self.result.emit(final_text)
                self.status.emit("完了しました！")
                
        except Exception as e:
            self.error.emit(f"エラーが発生しました: {str(e)}")
    
    def clean_text(self, text):
        """PDFから抽出したテキストを整形"""
        # 行末のハイフンを処理（単語の途中で改行されている場合）
        text = re.sub(r'-\n', '', text)
        
        # 段落内の改行を削除（文の途中の改行）
        lines = text.split('\n')
        cleaned_lines = []
        current_paragraph = []
        
        for line in lines:
            line = line.strip()
            if not line:
                # 空行は段落の区切り
                if current_paragraph:
                    cleaned_lines.append(' '.join(current_paragraph))
                    current_paragraph = []
                cleaned_lines.append('')
            else:
                # 前の行が文末記号で終わっているか確認
                if current_paragraph and not re.search(r'[.!?:]\s*$', current_paragraph[-1]):
                    # 文の途中なので結合
                    current_paragraph.append(line)
                else:
                    # 新しい文の開始
                    if current_paragraph:
                        cleaned_lines.append(' '.join(current_paragraph))
                        current_paragraph = []
                    current_paragraph.append(line)
        
        if current_paragraph:
            cleaned_lines.append(' '.join(current_paragraph))
        
        return '\n'.join(cleaned_lines)
    
    def is_english_text(self, text):
        """テキストが主に英語かどうかを判定"""
        ascii_chars = sum(1 for c in text if ord(c) < 128)
        japanese_chars = sum(1 for c in text if ord(c) > 0x3000)
        
        total_chars = len(text.strip())
        if total_chars == 0:
            return False
        
        # アルファベットが70%以上なら英語と判定
        return (ascii_chars / total_chars) > 0.7
    
    def translate_text_mymemory(self, text):
        """MyMemory翻訳APIを使用（文単位で翻訳）"""
        # 段落ごとに分割
        paragraphs = text.split('\n')
        translated_paragraphs = []
        
        for paragraph in paragraphs:
            if not paragraph.strip():
                translated_paragraphs.append('')
                continue
            
            # 文単位で分割（ピリオド、疑問符、感嘆符で分割）
            sentences = re.split(r'(?<=[.!?])\s+', paragraph)
            translated_sentences = []
            
            for sentence in sentences:
                if not sentence.strip():
                    continue
                
                # 500文字ごとに分割（APIの制限）
                if len(sentence) > 500:
                    chunks = [sentence[i:i+500] for i in range(0, len(sentence), 500)]
                else:
                    chunks = [sentence]
                
                for chunk in chunks:
                    retry_count = 0
                    max_retries = 3
                    
                    while retry_count < max_retries:
                        try:
                            url = "https://api.mymemory.translated.net/get"
                            params = {
                                'q': chunk.strip(),
                                'langpair': 'en|ja'
                            }
                            
                            full_url = url + '?' + urllib.parse.urlencode(params)
                            
                            with urllib.request.urlopen(full_url, timeout=15) as response:
                                data = json.loads(response.read().decode('utf-8'))
                                
                                if data['responseStatus'] == 200:
                                    translated_sentences.append(data['responseData']['translatedText'])
                                    break
                                else:
                                    # レート制限の場合は待機してリトライ
                                    if retry_count < max_retries - 1:
                                        time.sleep(1)
                                        retry_count += 1
                                    else:
                                        translated_sentences.append(chunk)  # 原文を返す
                                        break
                            
                            # APIレート制限対策
                            time.sleep(0.3)
                            
                        except Exception as e:
                            if retry_count < max_retries - 1:
                                time.sleep(1)
                                retry_count += 1
                            else:
                                translated_sentences.append(chunk)  # 原文を返す
                                break
            
            # 文を結合
            translated_paragraphs.append(''.join(translated_sentences))
        
        return '\n'.join(translated_paragraphs)


class PDFDropWidget(QWidget):
    file_dropped = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        
        layout = QVBoxLayout()
        
        self.drop_label = QLabel("PDFファイルをここにドラッグ&ドロップ\n\n英語PDFは自動で日本語に翻訳されます")
        self.drop_label.setAlignment(Qt.AlignCenter)
        self.drop_label.setStyleSheet("""
            QLabel {
                border: 3px dashed #aaa;
                border-radius: 10px;
                padding: 50px;
                font-size: 18px;
                color: #666;
                background-color: #f9f9f9;
            }
        """)
        
        layout.addWidget(self.drop_label)
        self.setLayout(layout)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
            self.drop_label.setStyleSheet("""
                QLabel {
                    border: 3px dashed #4CAF50;
                    border-radius: 10px;
                    padding: 50px;
                    font-size: 18px;
                    color: #4CAF50;
                    background-color: #e8f5e9;
                }
            """)
        else:
            event.ignore()
    
    def dragLeaveEvent(self, event):
        self.drop_label.setStyleSheet("""
            QLabel {
                border: 3px dashed #aaa;
                border-radius: 10px;
                padding: 50px;
                font-size: 18px;
                color: #666;
                background-color: #f9f9f9;
            }
        """)
    
    def dropEvent(self, event: QDropEvent):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        
        if files and files[0].lower().endswith('.pdf'):
            self.file_dropped.emit(files[0])
        
        self.drop_label.setStyleSheet("""
            QLabel {
                border: 3px dashed #aaa;
                border-radius: 10px;
                padding: 50px;
                font-size: 18px;
                color: #666;
                background-color: #f9f9f9;
            }
        """)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF翻訳アプリ")
        self.setGeometry(100, 100, 900, 700)
        
        # メインウィジェット
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        layout = QVBoxLayout()
        
        # タイトル
        title = QLabel("📄 PDF読み取り＆翻訳アプリ")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333; padding: 10px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # 説明
        description = QLabel("文章構造を認識 | 1ページずつ順番に処理 | MyMemory API")
        description.setStyleSheet("font-size: 12px; color: #999; padding: 0px;")
        description.setAlignment(Qt.AlignCenter)
        layout.addWidget(description)
        
        # ドロップエリア
        self.drop_widget = PDFDropWidget()
        self.drop_widget.file_dropped.connect(self.process_pdf)
        layout.addWidget(self.drop_widget)
        
        # ステータスラベル
        self.status_label = QLabel("待機中...")
        self.status_label.setStyleSheet("font-size: 14px; color: #666; padding: 5px;")
        layout.addWidget(self.status_label)
        
        # プログレスバー
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #ddd;
                border-radius: 5px;
                text-align: center;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 結果表示エリア
        result_label = QLabel("📖 翻訳結果")
        result_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333; padding: 10px 5px 5px 5px;")
        layout.addWidget(result_label)
        
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 10px;
                font-size: 13px;
                background-color: white;
                line-height: 1.6;
            }
        """)
        layout.addWidget(self.result_text)
        
        # ボタンレイアウト
        button_layout = QVBoxLayout()
        
        # 保存ボタン
        self.save_button = QPushButton("💾 結果をテキストファイルに保存")
        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        """)
        self.save_button.clicked.connect(self.save_results)
        self.save_button.setVisible(False)
        button_layout.addWidget(self.save_button)
        
        # クリアボタン
        self.clear_button = QPushButton("🗑️ 結果をクリア")
        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        self.clear_button.clicked.connect(self.clear_results)
        self.clear_button.setVisible(False)
        button_layout.addWidget(self.clear_button)
        
        layout.addLayout(button_layout)
        
        main_widget.setLayout(layout)
        
        self.translator_thread = None
    
    def process_pdf(self, pdf_path):
        self.result_text.clear()
        self.status_label.setText(f"処理中: {pdf_path}")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        self.clear_button.setVisible(False)
        self.save_button.setVisible(False)
        
        # 翻訳スレッド開始（1ページずつ順番に処理）
        self.translator_thread = TranslatorThread(pdf_path)
        self.translator_thread.progress.connect(self.update_progress)
        self.translator_thread.status.connect(self.update_status)
        self.translator_thread.result.connect(self.show_result)
        self.translator_thread.error.connect(self.show_error)
        self.translator_thread.start()
    
    def update_progress(self, value):
        self.progress_bar.setValue(value)
    
    def update_status(self, text):
        self.status_label.setText(text)
    
    def show_result(self, text):
        self.result_text.setText(text)
        self.clear_button.setVisible(True)
        self.save_button.setVisible(True)
        self.progress_bar.setVisible(False)
    
    def show_error(self, error_text):
        self.result_text.setText(f"❌ エラー:\n{error_text}")
        self.status_label.setText("エラーが発生しました")
        self.progress_bar.setVisible(False)
    
    def clear_results(self):
        self.result_text.clear()
        self.status_label.setText("待機中...")
        self.clear_button.setVisible(False)
        self.save_button.setVisible(False)
    
    def save_results(self):
        from PyQt5.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "翻訳結果を保存",
            "translated_result.txt",
            "テキストファイル (*.txt)"
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.result_text.toPlainText())
                
                QMessageBox.information(self, "保存完了", f"ファイルを保存しました:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "保存エラー", f"保存に失敗しました:\n{str(e)}")


def main():
    app = QApplication(sys.argv)
    
    # アプリケーションスタイル
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    print("PDF翻訳アプリを起動しました")
    print("必要なライブラリ:")
    print("  pip install PyQt5 PyPDF2")
    print("\n機能:")
    print("  ✓ 文章構造を認識（ピリオド・句読点で判定）")
    print("  ✓ 複数行にまたがる文も正しく翻訳")
    print("  ✓ 1ページずつ順番に処理（安定動作）")
    print("  ✓ MyMemory API（無料・安定）")
    print("  ✓ エラー時の自動リトライ機能")
    
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()