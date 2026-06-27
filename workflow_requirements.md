# Workflow Requirements — AI Job Application Automation System

## 1. Purpose
This document defines the functional and non-functional requirements for the automated job application document generation pipeline.

## 2. Input Requirements

### 2.1 Job Listings (Excel)
- **Format**: `.xlsx` with a single sheet
- **Required columns** (any of these aliases accepted):
  - `Company` / `company`
  - `Job_Title` / `Job Title` / `job_title` / `Position`
  - `Location` / `location`
  - `Job_Description` / `Job Description` / `job_description`
  - `Required_Skills` / `Required Skills` / `required_skills`
  - `Application_URL` / `Application URL` / `application_url`
- **Optional columns**: `Match_Score`, `Preferred_Qualifications`, `Key_Matching_Skills`, `Missing_Skills`, `Job_Type`, `Deadline`, `Source`, `Posting_Date`
- **Data quality**: Each row must represent a unique job posting; duplicates will be flagged automatically

### 2.2 Candidate Profile (JSON)
- **Files**: `profile/master_resume.json`, `profile/experience.json`, `profile/skills.json`, `profile/projects.json`
- **Content**: Name, contact, education, technical skills, work experience, projects, languages, certifications, research interests
- **Updates**: Profile files must be kept current before each run

## 3. Processing Pipeline

### 3.1 Stage 1 — Load & Normalize
- Read Excel input
- Normalize column names to standard lowercase snake_case
- Validate presence of required columns (`company`, `job_title`, `location`, `job_description`)
- Log warnings for missing columns but continue processing

### 3.2 Stage 2 — Deduplicate
- Exact URL match detection (100% similarity)
- Fuzzy company + title matching (RapidFuzz ratio ≥ 95%)
- Semantic description comparison (optional, via sentence-transformers)
- Required skills overlap scoring
- Mark duplicates with `duplicate=True`, `duplicate_of=<index>`, `deduplication_reason=<string>`
- Duplicates are skipped in document generation but retained in final output for reference

### 3.3 Stage 3 — Match Analysis
- For each unique job, compute a composite match score (0–100%):
  - **Education** (20%): Master's degree alignment, PhD penalty, Bachelor bonus
  - **Skills** (40%): Keyword overlap against candidate profile (Python, HPC, Quantum, ML, Cloud, Scientific Computing)
  - **Programming** (15%): Language match (Python, C/C++, JavaScript, Fortran, Julia, Go)
  - **Research** (15%): Research keywords, HPC/Quantum relevance, publication check
  - **Experience** (10%): Years required vs. candidate level, internship/thesis friendliness
- **Thresholds**:
  - `≥ 60%` → **proceed** (generate documents)
  - `50–59%` → **review** (flag for manual review)
  - `< 50%` → **skip** (no documents generated)
- Output per job: `match_percent`, `match_reasoning`, `missing_skills`, `strengths`, `status`

### 3.4 Stage 4 — Document Generation

#### Resume (LaTeX → PDF)
- Tailor professional summary to job themes (quantum, HPC, ML, simulation)
- Reorder and filter technical skills to top 8 most relevant
- Select top 3 most relevant projects
- Highlight relevant experience bullet points (up to 4 per role)
- Filter research interests to job-relevant topics
- Compile to single-page PDF via XeLaTeX
- Fallback: keep `.tex` source if PDF compilation fails

#### Cover Letter (DOCX)
- Header with candidate contact info
- Date, company name, position reference line
- Salutation: "Dear {Company} Hiring Team,"
- Opening paragraph: role-specific hook + strength alignment
- Technical qualifications paragraph: dynamically built from job keywords
- Experience paragraph: most recent role highlight
- Projects paragraph: most relevant project
- Motivation paragraph: company-specific
- Closing + signature
- Output: Microsoft Word `.docx`

### 3.5 Stage 5 — Excel Update
- Write all results back to output Excel
- Columns added: `match_percent`, `match_reasoning`, `missing_skills`, `strengths`, `status`, `resume_tex`, `resume_pdf`, `cover_letter`, `generated_date`
- File paths converted to `HYPERLINK()` formulas for one-click access
- Column widths auto-adjusted for readability

## 4. Output Requirements

| Output | Format | Location | Quality Criteria |
|--------|--------|----------|-----------------|
| Updated Excel | `.xlsx` | `output/Job_Matching_Updated.xlsx` | All rows present, hyperlinks functional, match scores filled |
| Resumes (source) | `.tex` | `generated/CV/tex/` | Valid LaTeX, ATS-optimized, ≤ 1 page |
| Resumes (compiled) | `.pdf` | `generated/CV/pdf/` | Readable PDF, correct formatting |
| Cover letters | `.docx` | `generated/CoverLetters/docx/` | Proper formatting, tailored content |
| Execution log | `.log` | `generated/Logs/generation.log` | Complete audit trail, errors captured |

## 5. Non-Functional Requirements

- **Concurrency**: Up to 4 parallel workers (configurable)
- **Error handling**: Per-job exception catching; failures logged, other jobs continue
- **Logging**: Structured log with timestamp, level, module name, message
- **Reproducibility**: Same input + same profile = same output (deterministic matching)
- **ATS compliance**: No images, tables, icons, or special characters in resumes
- **Performance**: 50 jobs should process in under 5 minutes on standard hardware

## 6. Error Handling & Recovery

| Scenario | Behavior |
|----------|----------|
| Missing Excel file | Try alternative filenames, then error and exit |
| Missing profile JSON | Skip that section, continue with available data |
| LaTeX compilation failure | Keep `.tex` source, log error, continue |
| DOCX generation failure | Log error, continue with other jobs |
| Sentence-transformers unavailable | Fall back to fuzzy-only deduplication |
| Empty job description | Log warning, use available fields for matching |

## 7. Workflow Diagram

```
Input Excel → Load & Normalize → Deduplicate → Match Analysis → Document Generation → Excel Update
                                    ↓              ↓                  ↓
                              Duplicates     Skip (<60%)       Resume (PDF)
                              flagged        Review (50-59%)     Cover Letter (DOCX)
```

## 8. Configuration

All behavior is controlled via `config.yaml`:
- `minimum_match_score`: 60 (default)
- `duplicate_similarity_threshold`: 0.95
- `generation.max_workers`: 4
- `generation.compile_latex`: true
- `paths.*`: Input/output directories
- `model.*`: AI model provider settings (optional, for future enhancement)

## 9. Validation Checklist

- [ ] Input Excel loaded successfully with all 50 rows
- [ ] Column normalization correct (no missing required columns)
- [ ] Duplicate detection finds 0–5 duplicates (expected for 50-job dataset)
- [ ] Match scores computed for all unique jobs
- [ ] Jobs with score < 60% skipped (no documents generated)
- [ ] Jobs with score ≥ 60% have resume and cover letter generated
- [ ] PDF compilation successful for all generated resumes
- [ ] Output Excel contains hyperlinks to all generated files
- [ ] Log file contains no unhandled exceptions
- [ ] Total processing time < 5 minutes
