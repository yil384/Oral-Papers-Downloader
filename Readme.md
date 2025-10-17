# 📦 1. Installation

```bash
pip install -r requirements.txt
```

# 🚀 2. Run the Program

```bash
python main.py
```
---

# ⚙️ Additional Usage

*(You can skip this section if the above commands run without errors.)*

## 1. Quick Run Without Installation (Using a Virtual Environment)

```bash
chmod +x run.sh
./run.sh
```

## 2. Download Papers from a Specific Conference

```bash
python main.py -c {conference_name} -y {year}
```

### Example:

```bash
python main.py -c neurips -y 2025
```

# ✅ Completed Tasks

* [x] **ICLR** – The 2025 “OpenReview” buttons are placeholders; the URLs do not exist.
* [x] **NeurIPS** – The 2025 official website has not yet uploaded the papers.
* [x] **ICML** – The 2024 version has no “OpenReview” button; 2023 has no “OpenReview” but includes a “PDF” button.
* [x] **CVPR** – The page layout differs from the others and uses lazy loading (papers are loaded as you scroll), which requires special handling.
