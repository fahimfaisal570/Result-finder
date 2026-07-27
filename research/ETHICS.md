# Institutional Data Privacy & Ethics Specification

Formal privacy, anonymization, and ethical data governance guidelines for academic research utilizing Result Finder PRO.

---

## 1. Student Anonymization Protocol

### Cryptographic Hashing
All student registration numbers ($R$) exported for research or dataset evaluation are anonymized using one-way SHA-256 cryptographic hashing with a per-deployment salt ($S$):

$$H_{\text{anon}} = \text{SHA256}(S \parallel R)[:16]$$

- **Salt Management**: The salt $S$ is stored exclusively in the deployment environment variable `RESEARCH_ANON_SALT` and is **never** committed to version control repositories.
- **Irreversibility**: The salt prevents rainbow table attacks and guarantees zero exposure of raw student registration numbers in public benchmarks or dataset dumps.

---

## 2. Privacy & Data Minimization

- **No Personal Identifiable Information (PII) Export**: Names, mobile phone numbers, and email addresses are stripped during dataset generation.
- **Aggregated Reporting**: Institutional dashboards and visual plots present aggregated batch-level metrics (cohort mean, standard deviation) rather than individual student records whenever possible.
- **Minimal Retention**: Raw web scraping HTML payloads are parsed in memory and discarded. Raw JSON cache records in the SQLite database retain only parsed academic records.

---

## 3. Automated Inference Risks & Ethical Mitigations

1. **Risk of Early Labeling**: Classifying a student as `At-Risk` or `Declining` must not lead to automated punitive measures.
   - *Mitigation*: All classifications include confidence scores and human-readable explanation strings (`research/explainer.py`).
2. **Institutional Governance**: Result Finder PRO analytics are intended solely for faculty academic advisory, curriculum planning, and authorized institutional research.
3. **Acceptable Use Policy**: Unauthorized public exposure, commercial resale, or individual student ranking for public shaming is strictly prohibited.
