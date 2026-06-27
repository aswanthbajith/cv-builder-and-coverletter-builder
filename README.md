# AI Job Application Automation System

Automatically process job listings from Excel, score them against your profile, generate ATS-optimized resumes (LaTeX → PDF) and tailored cover letters (DOCX), and update the spreadsheet with clickable links to every generated document.

## Features

- **Duplicate Detection** — Fuzzy string matching + optional semantic embeddings to remove duplicate job postings
- **Smart Matching** — Scores jobs on education, skills, programming, research, and experience alignment
- **ATS-Optimized Resumes** — LaTeX-based, single-page, keyword-optimized, no graphics/icons
- **Tailored Cover Letters** — Company-specific, role-specific DOCX generation
- **Automatic PDF Compilation** — XeLaTeX integration
- **Excel Hyperlinks** — Click to open generated documents directly from the spreadsheet
- **Concurrent Processing** — Configurable ThreadPoolExecutor workers
- **Comprehensive Logging** — Full audit trail in `generated/Logs/generation.log`

## Quick Start

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 2. Install LaTeX (for PDF compilation)

**Ubuntu/Debian:**
```bash
sudo apt-get install texlive-xetex texlive-fonts-recommended texlive-latex-extra
```

**macOS:**
```bash
brew install --cask mactex
```

**Windows:**
Download MiKTeX from https://miktex.org/

### 3. Configure Environment

Copy `.env.example` to `.env` and add your API keys (optional):
```bash
cp .env.example .env
```

Edit `config.yaml` to adjust thresholds, paths, and model settings.

### 4. Add Your Profile

Edit files in `profile/`:
- `master_resume.json` — Your complete profile, education, skills, projects
- `experience.json` — Work experience (or keep inside master_resume.json)
- `skills.json` — Technical skills list
- `projects.json` — Academic/projects list

### 5. Add Job Listings

Place your Excel file in `input/` (e.g., `jobs.xlsx`). The loader will auto-detect columns like `Company`, `Job Title`, `Location`, `Job Description`, etc.

### 6. Run

```bash
python src/main.py
```

## Output

- `generated/CV/pdf/` — Compiled PDF resumes
- `generated/CV/tex/` — LaTeX source files
- `generated/CoverLetters/docx/` — Word cover letters
- `output/Job_Matching_Updated.xlsx` — Updated spreadsheet with match scores, reasoning, missing skills, and hyperlinks to documents

## Docker

```bash
docker-compose up --build
```

## Project Structure

```
JobAutomation/
├── input/              # Input Excel files
├── profile/            # Your candidate profile (JSON)
├── templates/          # LaTeX and DOCX templates
│   └── cv_template.tex
├── generated/          # Output documents
│   ├── CV/
│   │   ├── pdf/
│   │   └── tex/
│   ├── CoverLetters/
│   │   └── docx/
│   └── Logs/
│       └── generation.log
├── output/             # Final Excel with hyperlinks
├── src/                # Source code
│   ├── config.py
│   ├── excel_loader.py
│   ├── deduplicator.py
│   ├── matcher.py
│   ├── resume_generator.py
│   ├── cover_letter_generator.py
│   ├── latex_compiler.py
│   ├── excel_updater.py
│   └── main.py
├── tests/
│   └── test_automation.py
├── config.yaml         # Configuration
├── requirements.txt    # Dependencies
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md           # This file
```

## Configuration (`config.yaml`)

| Key | Description | Default |
|-----|-------------|---------|
| `minimum_match_score` | Jobs below this score are skipped | 60 |
| `duplicate_similarity_threshold` | Duplicate detection cutoff | 0.95 |
| `model.provider` | AI model provider (gemini/openai/ollama) | gemini |
| `generation.max_workers` | Parallel processing threads | 4 |
| `generation.compile_latex` | Compile PDFs via XeLaTeX | true |
| `paths.input_excel` | Input Excel path | input/jobs.xlsx |
| `paths.output_excel` | Output Excel path | output/Job_Matching_Updated.xlsx |

## Running Tests

```bash
python -m unittest tests/test_automation.py
```

## Troubleshooting

**LaTeX not found?** Install XeLaTeX and ensure `xelatex` is on your system PATH. On Windows, add MiKTeX's `bin` directory to PATH.

**No Excel file found?** Ensure `input/jobs.xlsx` exists, or update `config.yaml` → `paths.input_excel`.

**sentence-transformers fails?** The deduplicator gracefully falls back to fuzzy matching only if the model cannot be loaded.

## License

MIT License
