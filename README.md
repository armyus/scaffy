# 🐾 Scaffy — Proactive Local AI Desktop Reading Companion

Scaffy is an always-on-top, ambient AI desktop companion designed to help readers, developers, and researchers digest dense technical papers, documentation, and mathematical formulas effortlessly and locally.

---

## ✨ Features

- 🧠 **100% Local CPU Inference**: Powered by `llama-cpp-python` loading `qwen2.5-0.5b-instruct-q4_k_m.gguf` strictly on CPU (`n_gpu_layers=0`). No cloud APIs, no subscriptions, zero data leaves your machine.
- ⚡ **Instant Highlight Capture**: Highlight any word, sentence, or multi-line paragraph in your PDF reader or browser. The moment you release the mouse, Scaffy non-destructively reads and breaks it down without vanishing your highlight.
- ⏱️ **Proactive Hover & Friction Sensors**:
  - **Word Dwell (5.0s)**: Pausing over an unfamiliar technical term triggers an intuitive definition.
  - **Paragraph Reading Friction (15.0s)**: Detects reading stalls across complex paragraphs and breaks down the core concepts.
  - **Keystroke & Tab Suppression**: Automatically pauses when typing or switching applications.
- 📖 **Interactive Vector Companion**:
  - Vector mascot holding an open book and reading along with you.
  - **Petting Interaction**: Rubbing/hovering rapidly over Scaffy enters a purring state with happy closed eyes (`^ ^`), blush, and soft synthesized purrs.
  - **Double-Click Spark**: Double-clicking triggers a celebratory 360° backflip mini-animation and a rotating, non-repeating deck of inspiring reading quotes.
  - **In-Memory Cat Acoustics**: Cozy, synthesized kitten vocalizations (`mrrp`, `purr`, `meow`, `chirp`) using Python's standard `wave` and `winsound`.
  - **Mute Toggle**: Easily toggle audio from the bubble header or right-click context menu.

---

## 🚀 Quick Start

### 1. Prerequisites
- **Python 3.10+** (Windows 10/11)
- Intel Core i5 / AMD equivalent CPU, 8 GB RAM (No dedicated GPU required)

### 2. Installation
```powershell
# Clone the repository
git clone <your-repo-url>
cd scaffy

# Create and activate a virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. Download the Model
Download the quantized GGUF weights into the root directory:
- **Model**: `qwen2.5-0.5b-instruct-q4_k_m.gguf` (~491 MB)
- Place the file directly in `scaffy/qwen2.5-0.5b-instruct-q4_k_m.gguf`.

### 4. Launch Scaffy
```powershell
python scaffy_pet.py
```

---

## 🧪 Tests
Run the built-in parser and cache unit test suite:
```powershell
python test_scaffy_pet.py
```

---

## 📜 License
MIT License.
