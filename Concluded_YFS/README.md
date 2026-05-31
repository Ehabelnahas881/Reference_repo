# 🚀 Yahoo Finance Suite (YFS) Engine

A fully integrated, multi-strategy financial data acquisition engine designed to navigate the complexities of **Yahoo Finance (YFS)**. This suite provides 24/7 high-fidelity market data through various extraction vectors, ensuring maximum uptime and anti-bot resilience.

---

## 🔍 Data Acquisition Matrix
The engine utilizes three distinct strategic positions to obtain data from YFS:

1.  **📊 Chart Analysis**: Direct extraction of interactive graphical data.
2.  **🏷️ Selector Logic**: Targeted scraping based on dynamic Session IDs (Overnight, Pre, Regular, Post).
3.  **🔌 JSON API**: Intercepting backend data streams for pure numerical precision.

---

## 🛠️ Core Technology Stack

| Library | Methodology | Primary Advantage |
| :--- | :--- | :--- |
| **BS4** | BeautifulSoup 4 | Ultra-lightweight parsing with minimal CPU overhead. |
| **SE** | Selenium | High-fidelity interaction with JavaScript-heavy elements. |
| **curl-cffi** | Advanced Requests | TLS/JA3 Fingerprint impersonation to bypass pro-level bot blocks. |

---

## 📂 Module Breakdown

### 💎 YFS_Engine_app
**The Orchestrator.**  
The central nervous system of the suite. It acts as the fully integrated API distributor, managing the synchronization between the **Scrapers**, the **Server**, and the **Settings** environment.

### ⚡ YFS_BS4_curl_cffi.py
*   **Methodology**: `BeautifulSoup` + `curl-cffi`
*   **Verdict**: **The Gold Standard.**
*   **Description**: This is the most effective and stable strategy within the suite. By utilizing `curl-cffi`, it mimics real browser signatures at the network level, making it the most resilient tool against Yahoo’s modern security layers.

### 📨 YFS_BS4_request.py
*   **Methodology**: `BeautifulSoup` + `Requests`
*   **Verdict**: **Efficiency Focused.**
*   **Description**: A streamlined evolution designed to reduce the high request overhead associated with Selenium. Ideal for high-frequency updates where network bandwidth is a constraint.

### 📈 YFS_SE_chart.py
*   **Methodology**: `Selenium` (Visual Chart Scraping)
*   **Verdict**: **The Reliable Traditionalist.**
*   **Description**: While resource-heavy, this is the most dependable method for obtaining **'Volume'** data, as it extracts information directly from the rendered interactive canvas.

### 🛡️ YFS_SE_json.py (The Hybrid Tank)
*   **Methodology**: `Selenium` + `JSON API` + `Selector Mutation`
*   **Verdict**: **The Ultimate 24h Solution.**
*   **Description**: Specifically engineered for **AWS POD** stability. It utilizes a sophisticated **Mutation Logic**:
    *   **Daytime**: Leverages the **JSON API** for the 3 regular market sessions to provide the highest data accuracy.
    *   **Nighttime**: Mutates into **Selector Scraping** to capture the **Overnight Session** directly from website elements when APIs are restricted.
    *   **Result**: 100% uptime with built-in resilience against IP blocks and bot detection.

---

## 🚀 Deployment Strategy
Designed to run 24/7 on **Cloud/K8s (AWS Pods)**. The suite features:
*   **Low Footprint**: Optimized to prevent "POD Overwhelm."
*   **Session Awareness**: Intelligent switching between Blue Ocean (Overnight) and Regular sessions.
*   **Error Recovery**: Hardened logic to handle RDS connection drops and HTTP 403 retries.

---
📫 **Architected for Professional Financial Data Engineering.**
