# System Methods & Formal Specifications

Formal methodology definitions for all underlying algorithms, mathematical models, and system mechanisms in Result Finder PRO (`v2`).

---

## 1. Web Scraping & Connection Management Algorithm

### Overview
The web data extraction subsystem executes automated HTTP requests against the target university portal using persistent `requests.Session` connections with exponential backoff and randomized user-agent headers to minimize WAF friction.

### Mathematical Formulation
For network request attempt $i \in \{1, 2, \dots, N_{\text{max}}\}$, the delay $\tau_i$ before retry is defined as:
$$\tau_i = 2^{i-1} + U(0.1, 0.5) \quad \text{seconds}$$
where $U(a, b)$ is a uniform random jitter value.

If global rate limiting triggers (HTTP 429 or connection reset), a global backoff lock is set for $T_{\text{backoff}} = 15.0$ seconds.

---

## 2. Subject-Overlap Fingerprinting & Re-Admission Identification

### Overview
Detects senior batch students who have dropped down into lower-semester classes (re-admitted students) versus students attempting one-off retake/improvement exams (retake ghosts).

### Algorithm
Let $R$ be the set of valid regular students in the target batch, and $S(r)$ be the set of subject codes for student $r \in R$.

1. **Reference Fingerprint Construction**:
   Find all subject codes $c$ appearing with frequency threshold $\ge 30\%$ among regular students:
   $$F_{\text{ref}} = \left\{ c \;\middle|\; \frac{\sum_{r \in R} \mathbb{I}(c \in S(r))}{|R|} \ge 0.30 \right\}$$

2. **Dual-Filter Evaluation**:
   For a candidate student $x$ with subject set $S(x)$:
   $$\text{Overlap Ratio} = \frac{|S(x) \cap F_{\text{ref}}|}{|F_{\text{ref}}|}$$
   $$\text{Load Ratio} = \frac{|S(x)|}{|F_{\text{ref}}|}$$

   Candidate $x$ is classified as **Re-Admitted** if and only if:
   $$\text{Overlap Ratio} \ge 0.50 \quad \land \quad \text{Load Ratio} \ge 0.70$$
   Otherwise, candidate $x$ is discarded as a **Retake/Improvement Ghost**.

---

## 3. True Credit-Weighted CGPA Reconstruction

### Overview
Reconstructs exact cumulative grade point average (CGPA) accounting for variable course credits, syllabus overrides, and retake grade replacements.

### Mathematical Model
Let $C_i$ be the credit hours for course $i$, and $G_i$ be the final effective grade point achieved in course $i$:
$$\text{True CGPA} = \frac{\sum_{i=1}^{K} C_i \cdot G_i}{\sum_{i=1}^{K} C_i}$$

Where retake attempts occur for course $i$, $G_i$ is updated to $\max(G_{i, \text{old}}, G_{i, \text{new}})$, preserving completed credit hours while updating grade points.

---

## 4. 50/50 Hybrid GPA Forecasting Model

### Overview
Forecasts future semester GPAs using a 50/50 blend of linear trend analysis and exponential moving average (EMA).

### Mathematical Model
Given completed semester GPAs $\{g_1, g_2, \dots, g_t\}$ for semesters $\{1, 2, \dots, t\}$:

1. **Linear Trend**:
   Fit linear regression line $y(s) = \beta_1 \cdot s + \beta_0$ via ordinary least squares (OLS):
   $$\hat{g}_{\text{linear}}(s) = \beta_1 \cdot s + \beta_0$$

2. **Exponential Moving Average (EMA)**:
   For recency weight $\alpha = 0.6$:
   $$e_1 = g_1, \quad e_k = \alpha \cdot g_k + (1 - \alpha) \cdot e_{k-1} \quad \text{for } k=2 \dots t$$

3. **Hybrid Prediction**:
   For target semester $s > t$:
   $$\hat{g}_{\text{hybrid}}(s) = \text{clip}\left( 0.5 \cdot \hat{g}_{\text{linear}}(s) + 0.5 \cdot e_t, \; 0.0, \; 4.0 \right)$$

---

## 5. Academic State Taxonomy

Students are categorized into strict research states based on performance metrics:
- **Regular**: Normal academic standing, standard course load.
- **Re-Admitted**: Student identified via subject fingerprinting as joining from a senior batch.
- **At-Risk**: CGPA falls below year promotion threshold ($Y_1: 2.00, Y_2: 2.25, Y_3: 2.50$).
- **High Performer**: $\text{CGPA} \ge 3.75$.
- **Declining**: Trend slope $\beta_1 < -0.15$ over 3+ semesters.
- **Retake Candidate**: Active failed or uncleared subjects remaining.
- **Stable**: $\Delta \text{CGPA} \le \pm 0.05$ across recent semesters.
