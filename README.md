# 📈 VN Stock Intelligence: Automated Cloud Data Lakehouse & GenBI Platform

> An end-to-end, cloud-native ELT pipeline and quantitative analytics platform designed to bridge the gap between financial news sentiment and daily market price actions across Vietnam's equity markets (HOSE/HNX).

[![Live Demo](https://img.shields.io/badge/Streamlit-Live_Demo-FF4B4B?style=flat&logo=streamlit)](https://vnstock-intelligence-and-sentiment-analysis.streamlit.app/)
[![Database](https://img.shields.io/badge/MotherDuck-Cloud_Data_Warehouse-B1B5C8?style=flat)](https://motherduck.com/)
[![Transformation](https://img.shields.io/badge/dbt--core-v1.8-FF694B?style=flat&logo=dbt)](https://www.getdbt.com/)
[![CI/CD](https://img.shields.io/badge/GitHub_Actions-Automated_ELT-2088FF?style=flat&logo=github-actions)](https://github.com/features/actions)

---

## 📌 Problem Statement & Objectives
Retail and institutional investors in the Vietnamese stock market often face:
1. **Information Asymmetry & Data Fragmentation:** Disconnect between high-frequency market news and quantitative price movements.
2. **Operational Overhead:** Manual data collection and lack of standardized data modeling for analytics-ready downstream tasks.

**Solution:** **VN Stock Intelligence** shifts from traditional batch ETL to a cloud-native **ELT Modern Data Lakehouse**, automating daily ingestion, enforcing Kimball dimensional modeling, and delivering instant market insights via RAG-assisted Generative BI.

---

## 🏗️ System Architecture

The platform is structured into four decoupled, production-grade layers:

```mermaid
flowchart LR
    subgraph S1[1. Data Sources]
        API[vnstock API<br/>10-Yr Historical & News]
    end

    subgraph S2[2. Ingestion - Bronze Layer]
        GHA[GitHub Actions<br/>Cron: 06:00 T3-T7] -->|ingest.py| MD_Raw[(MotherDuck<br/>Bronze Staging)]
        MD_Raw -->|UNION BY NAME + QUALIFY| MD_Dedup[Deduplicated Bronze]
    end

    subgraph S3[3. Transformation - Silver & Gold]
        DBT[dbt Core<br/>Lineage & Orchestration]
        MD_Dedup --> DBT
        DBT --> Stg[Silver Layer:<br/>Cleaned Staging Views]
        Stg --> Marts[Gold Layer:<br/>Kimball Star Schema<br/>dim_stock / fact_daily_prices / fact_news]
        Marts --> WideTable[analytics_wide_ai_ready]
    end

    subgraph S4[4. Intelligence & GenBI]
        WideTable --> ML[ML Sentiment Classifier<br/>LSA + Logistic Regression]
        WideTable --> RAG[RAG Engine + Groq Cloud API<br/>LLM Synthesis]
        ML --> App[Streamlit Cloud<br/>Interactive Dashboard & Chatbot]
        RAG --> App
    end

    S1 --> S2
