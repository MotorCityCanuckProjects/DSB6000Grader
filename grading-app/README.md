# Data Science Ethics - Graduate Paper Grading System

A locally-hosted web application that uses the OpenAI GPT-4o API to automatically grade graduate-level Data Science Ethics papers against a configurable rubric. Built with Python, Flask, and plain HTML/CSS/JavaScript.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Using the Application](#using-the-application)
- [Rubric Configuration](#rubric-configuration)
- [Grading Behavior](#grading-behavior)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)
- [Future Improvements](#future-improvements)

---

## Overview

This application is designed to assist instructors in grading graduate-level papers on Data Science Ethics. The instructor pastes the student's paper into a text window, and the application sends the paper to the OpenAI GPT-4o API along with the grading rubric. The API returns a detailed grade and feedback for each rubric category, which is displayed on the page.

The grading system is intentionally strict, holding students to high graduate-level academic standards. Scores above 90 are rare and reserved for truly exceptional work.

---

## Features

- **Rubric display** - The left panel displays the full grading rubric loaded from `rubric.yaml`, including each criterion name, point value, and description.
- **Paper submission** - The right panel accepts a student name and the full text of the paper to be graded.
- **Word count** - The application automatically counts and displays the number of words in the submitted paper.
- **AI-powered grading** - Uses OpenAI GPT-4o to evaluate the paper against the rubric with strict graduate-level standards.
- **Detailed feedback** - Provides 4-5 paragraphs of overall feedback and 5-6 sentences of specific feedback for each rubric criterion.
- **Score breakdown** - Displays the score earned for each rubric criterion alongside the feedback.
- **Total score** - Displays the total points earned out of the total possible points (e.g., 82/100).
- **Loading indicator** - Displays a spinner while the paper is being graded.
- **Error handling** - Displays user-friendly error messages if something goes wrong.
- **Configurable rubric** - The rubric is stored in a simple YAML file and can be easily updated without changing any code.

---

## Project Structure

```
grading-app/
├── app.py                  # Flask backend - routes and OpenAI API integration
├── rubric.yaml             # Grading rubric configuration file
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── templates/
│   └── index.html          # Main HTML page (Jinja2 template)
└── static/
    ├── css/
    │   └── styles.css      # Stylesheet - layout, fonts, colors
    └── js/
        └── app.js          # Frontend JavaScript - API calls and UI updates
```

---

## Requirements

- Python 3.8 or higher
- An OpenAI API key with access to GPT-4o
- An internet connection (for the OpenAI API call)
- A modern web browser (Chrome, Firefox, Edge, Safari)

---

## Installation

### 1. Clone or download the repository

```
git clone https://github.com/your-username/grading-app.git
cd grading-app
```

### 2. Create and activate a Python virtual environment

**Windows (PowerShell):**
```
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```
python3 -m venv venv
source venv/bin/activate
```

### 3. Install the required dependencies

```
pip install -r requirements.txt
```

The following packages will be installed:

| Package   | Purpose                              |
|-----------|--------------------------------------|
| `flask`   | Web framework for the backend server |
| `openai`  | OpenAI API client                    |
| `pyyaml`  | YAML parser for loading the rubric   |

---

## Configuration

### Setting the OpenAI API Key

The application requires an OpenAI API key to communicate with GPT-4o. The key must be set as an environment variable before running the app.

**Windows (PowerShell):**
```
$env:OPENAI_API_KEY="your-api-key-here"
```

**Windows (Command Prompt):**
```
set OPENAI_API_KEY=your-api-key-here
```

**macOS/Linux:**
```
export OPENAI_API_KEY="your-api-key-here"
```

> **Important:** Never hardcode your API key directly in the source code or commit it to version control. Always use environment variables.

You can obtain an API key from the [OpenAI Platform](https://platform.openai.com/api-keys).

---

## Running the Application

Once the environment variable is set and the dependencies are installed, start the application by running:

```
python app.py
```

You should see the following output in the terminal:

```
============================================================
  Data Science Ethics - Paper Grading Application
============================================================
  Running at: http://127.0.0.1:5000
============================================================
```

Open your web browser and navigate to:

```
http://127.0.0.1:5000
```

---

## Using the Application

1. **Review the Rubric** - The left panel displays the grading rubric. Review the criteria and point values before grading.

2. **Enter the Student Name** - Type the student's name in the "Student Name" field on the right panel.

3. **Paste the Paper** - Copy the full text of the student's paper and paste it into the large "Paper Text" textarea.

4. **Click "Grade Paper"** - Click the button to submit the paper for grading. A loading spinner will appear while the paper is being evaluated by GPT-4o. This may take 15-30 seconds depending on paper length.

5. **Review the Results** - Once grading is complete, the results section will appear below the panels, showing:
   - The student's name
   - The total score (e.g., 78/100)
   - The word count of the submitted paper
   - 4-5 paragraphs of overall feedback
   - A breakdown of the score and feedback for each rubric criterion

6. **Grade Another Paper** - Click the "Grade Another Paper" button to clear the form and start again.

---

## Rubric Configuration

The grading rubric is stored in `rubric.yaml` in the root of the project. You can modify this file to change the criteria, point values, or descriptions without touching any code.

### Rubric File Format

```yaml
total_points: 100
criteria:
  - name: Criterion Name
    points: 25
    description: A description of what this criterion evaluates and what is expected.

  - name: Another Criterion
    points: 25
    description: A description of what this criterion evaluates and what is expected.
```

### Current Rubric Criteria

| Criterion | Points |
|-----------|--------|
| Understanding of Ethical Concepts - Clarity & Accuracy | 15 |
| Understanding Ethical Concepts - Application to Data Science | 15 |
| Critical Analysis and Reasoning - Identification of Ethical Dilemmas | 15 |
| Critical Analysis & Reasoning - Logical Argumentation | 15 |
| Critical Analysis & Reasoning - Consideration of Diverse Perspectives | 10 |
| Practical Implications & Solutions - Proposed Solutions or Recommendations | 10 |
| Practical Implications & Solutions - Awareness of Responsibility | 5 |
| Written Communications | 8 |
| Written Communication - Grammar & Mechanics | 7 |
| **Total** | **100** |

> **Note:** After modifying `rubric.yaml`, restart the Flask application for the changes to take effect.

---

## Grading Behavior

The application instructs GPT-4o to grade papers with strict graduate-level standards using the following guidelines:

| Score Range | Meaning |
|-------------|---------|
| 95+         | Rare - truly outstanding work that exceeds all expectations |
| 80-89       | High quality work that exceeds rubric expectations |
| 70-79       | Adequate but unremarkable graduate-level work |
| Below 70    | Superficial treatment of topics - points deducted |

The AI evaluator is instructed to:
- Never give the benefit of the doubt for unclear or underdeveloped content
- Always deduct points for vague arguments, weak evidence, or surface-level analysis
- Cite specific passages from the paper to justify every score
- Provide 5-6 sentences of specific, actionable feedback per criterion

---

## API Reference

### `POST /api/grade`

Grades a paper using the OpenAI API.

**Request Body:**
```json
{
  "student_name": "Jane Smith",
  "paper_text": "The full text of the student paper..."
}
```

**Response Body:**
```json
{
  "student_name": "Jane Smith",
  "word_count": 1842,
  "grade": "78/100",
  "feedback": "Overall feedback paragraphs...",
  "criterion_feedback": [
    {
      "name": "Criterion Name",
      "points": 25,
      "score": 19,
      "feedback": "Detailed criterion feedback..."
    }
  ]
}
```

**Error Response:**
```json
{
  "error": "Error message describing what went wrong"
}
```

---

## Troubleshooting

### `OpenAIError: The api_key client option must be set`
Your `OPENAI_API_KEY` environment variable is not set. Follow the steps in the [Configuration](#configuration) section. Note that environment variables set in PowerShell or Command Prompt only persist for that session. You will need to set the variable again if you close and reopen the terminal.

### `ModuleNotFoundError: No module named 'flask'`
Your virtual environment is not activated or the dependencies are not installed. Run:
```
venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### The page loads but grading returns an error
- Ensure your OpenAI API key is valid and has access to GPT-4o.
- Check that `rubric.yaml` exists in the root of the project and is correctly formatted.
- Check the terminal output for any Python error messages.

### The rubric is not displaying on the page
- Ensure `rubric.yaml` is present in the root `grading-app/` directory.
- Verify the YAML file is correctly formatted (use consistent spacing, no tabs).
- Restart the Flask application after any changes to `rubric.yaml`.

### Grading takes a long time
This is expected. GPT-4o processes the full paper text along with the rubric and generates detailed feedback. Grading typically takes 15-45 seconds depending on the length of the paper.

---

## Future Improvements

- **PDF export** - Allow the instructor to download the grading results as a formatted PDF report.
- **Database storage** - Save grading results to a database for record-keeping and review.
- **Rubric editor** - Add a UI to edit the rubric directly from the web interface.
- **Batch grading** - Support uploading and grading multiple papers at once.
- **Authentication** - Add a login system to restrict access to authorized instructors.
- **Grade history** - View a history of all previously graded papers.
- **Customizable prompts** - Allow the instructor to adjust the grading strictness and feedback length from the UI.
