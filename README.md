# Evil AI Scraper

## Overview
This project features a web scraping and Natural Language Processing (NLP) pipeline designed to identify and document AI systems that are reported to be utilized for abusive or harmful purposes. The system is built to collect public reports, filter out relevant content, extract structured data, and leverage a Large Language Model (LLM) to generate standardized documentation.

---

## Architecture 
The system architecture consists of six primary components:
* **Web Scraper**: Collects articles and reports from credible sources.
* **NLP Filter**: Identifies relevant content related to misuse.
* **Extraction Layer**: Pulls descriptions, entities, and evidence from the text.
* **ML Scoring**: Assigns a confidence score regarding relevance.
* **LLM Layer**: Generates structured summaries based on the extracted data.
* **Database**: Stores the resulting structured data for further analysis.

---

## Processing Pipeline 
The data processing workflow follows these sequential steps:
1. Scrape web pages from trusted sources.
2. Clean and preprocess the extracted text.
3. Apply keyword and proximity filtering.
4. Score the content using a semantic embedding model.
5. Extract the specific entity and the description of the abuse.
6. Send the structured data to the LLM to generate documentation.

---

## Machine Learning & NLP Approach 
The project utilizes a hybrid approach for its ML and NLP tasks:
* Keyword-based filtering to ensure high recall.
* Sentence embeddings for deeper semantic understanding.
* Weak supervision for data labeling.
* Lightweight classifiers or logistic regression for relevance scoring.
* Active learning to iteratively enhance system performance.

### LLM Integration 
The LLM is strictly utilized for structured summarization rather than discovery. It receives the extracted fields to generate consistent documentation entries, avoiding hallucination by relying exclusively on the provided evidence.

---

## Data Schema 
The extracted and stored data follows this schema:
* `name` 
* `category` 
* `what_it_does` 
* `evidence_link` 
* `source` 
* `date` 
* `confidence` 
* `evidence_text` 
