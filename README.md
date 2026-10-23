# Website Quality Analyzer API

A lightweight, high-performance FastAPI backend that performs an automated website audit across 5 key pillars (Size & Speed, Social Proof, Forms/Quizzes, SEO Quality, and Contact Info), designed to integrate seamlessly with a Squarespace frontend via custom code injection.

## Features

- **Automated Speed & Size Heuristics:** Calculates page payload in KB and measures live response load time.
- **Social Proof Detection:** Scans text content and DOM elements for testimonials, reviews, and trust badges.
- **Form & Quiz Analyzer:** Detects standard web forms, multi-step wizards, and quiz indicators.
- **SEO Audit:** Verifies the presence of meta descriptions and computes image alt-text coverage ratios.
- **Contact Validation:** Detects valid email addresses and phone numbers.
- **Scored Breakdown:** Grades each metric from 1 to 10 and calculates a weighted overall score out of 100.

---

## Project Structure

```text
├── main.py              # FastAPI application and audit logic
├── requirements.txt     # Python dependencies
└── README.md            # Project documentation
