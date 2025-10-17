# 📦 1. Installation

```bash
pip install -r requirements.txt
```

# 🚀 2. Run the Program

```bash
python main.py
```

# 📖 3. View on the website

```bash
python -m http.server 8000 
```

Then you can visit http://localhost:8000/

---

# ⚙️ Additional Usage

*(You can skip this section if the above commands run without errors.)*

## 1. [TODO] Quick Run Without Installation (Using a Virtual Environment)

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

# ✅ Todo

* [ ] **ICLR** – The page source for 2022 and earlier years is different and requires special handling. The 2023 version has no "OpenReview" button; the 2025 "OpenReview" button is a fake link.
* [ ] **NeurIPS** – The page source for 2022 and earlier years is different and requires special handling. The 2025 version has not yet uploaded the oral paper display page.
* [ ] **ICML** – The 2024 version has no "OpenReview" button; 2023 has no "OpenReview" but includes a "PDF" button. The page source for 2024 and earlier years is different and requires special handling.
* [x] **CVPR** – The page layout differs from the others and uses lazy loading (papers are loaded as you scroll), which requires special handling. Oral papers from 2023 and earlier have not been found yet.
* [ ] Internationalization (English)
* [ ] Fix potential bugs such as: download failures, **first abstract not existing**, etc.