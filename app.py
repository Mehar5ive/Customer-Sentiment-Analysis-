import os
import pandas as pd
import nltk
import json
import io
import csv
from flask import Flask, request, jsonify, render_template, Response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, time
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from pypdf import PdfReader
from sqlalchemy import func
from collections import defaultdict
from werkzeug.utils import secure_filename

# -------------------- Initialization --------------------
app = Flask(__name__)

app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    "DATABASE_URL", "sqlite:///analysis_history.db"
)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# NLTK Setup 
try:
    nltk.data.find('sentiment/vader_lexicon')
except LookupError:
    nltk.download('vader_lexicon')

from nltk.sentiment.vader import SentimentIntensityAnalyzer
analyzer = SentimentIntensityAnalyzer()

# Custom Word Scores 
new_words = {
    'trash': -3.5, 'garbage': -3.5, 'unacceptable': -4.0,
    'disaster': -4.0, 'subpar': -3.0, 'brilliant': 3.5,
    'perfect': 4.0, 'not bad': 1.5,
}
analyzer.lexicon.update(new_words)

# Database Models 
class AnalysisRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    results_summary = db.Column(db.Text, nullable=False)
    entries = db.relationship(
        'FeedbackEntry',
        backref='run',
        lazy=True,
        cascade="all, delete-orphan"
    )

class FeedbackEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('analysis_run.id'), nullable=False)
    text = db.Column(db.String(5000), nullable=False)
    sentiment = db.Column(db.String(20))
    confidence = db.Column(db.Float)
    emotion = db.Column(db.String(20))
    category = db.Column(db.String(20))
    urgency = db.Column(db.String(20))

# NLP
def analyze_text(text):
    scores = analyzer.polarity_scores(text)

    sentiment = "Neutral"
    if scores['compound'] >= 0.05:
        sentiment = "Positive"
    elif scores['compound'] <= -0.05:
        sentiment = "Negative"

    confidence = scores['compound']
    text_lower = text.lower()

    emotion = "Neutral"
    if any(w in text_lower for w in ["angry", "hate", "furious", "unacceptable", "trash", "garbage"]):
        emotion = "Anger"
    elif any(w in text_lower for w in ["sad", "disappointed", "sorry", "disaster", "subpar"]):
        emotion = "Sadness"
    elif any(w in text_lower for w in ["love", "amazing", "joy", "fantastic", "brilliant", "perfect"]):
        emotion = "Joy"

    category = "General"
    if any(w in text_lower for w in ["product", "feature", "pricing"]):
        category = "Product"
    elif any(w in text_lower for w in ["service", "support", "agent"]):
        category = "Service"
    elif any(w in text_lower for w in ["delivery", "shipping", "package"]):
        category = "Delivery"

    urgency = "Normal"
    if any(w in text_lower for w in ["urgent", "critical", "asap"]):
        urgency = "Critical"
    elif any(w in text_lower for w in ["high priority", "soon"]):
        urgency = "High"

    return sentiment, confidence, emotion, category, urgency

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        source_name = ""
        feedback_list = []

        text_feedback = request.form.get('text_feedback')

        if text_feedback and text_feedback.strip():
            source_name = "Text Input"
            feedback_list = [
                line for line in text_feedback.split('\n') if line.strip()
            ]

        elif 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            filename = secure_filename(file.filename)

            source_name = f"File: {filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            try:
                file.save(filepath)

                if filepath.endswith('.csv'):
                    df = pd.read_csv(filepath)
                    feedback_list = df.iloc[:, 0].dropna().astype(str).tolist()

                elif filepath.endswith('.pdf'):
                    reader = PdfReader(filepath)
                    feedback_list = [
                        line.strip()
                        for line in "".join(p.extract_text() for p in reader.pages).split('\n')
                        if line.strip()
                    ]

                else:
                    return jsonify({"error": "Unsupported file"}), 400

            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)

        else:
            return jsonify({"error": "No input provided"}), 400

        # Process feedback
        summary = {"Positive": 0, "Negative": 0, "Neutral": 0}

        for text in feedback_list:
            sentiment, *_ = analyze_text(text)
            summary[sentiment] += 1

        return jsonify(summary)

    except Exception as e:
        return jsonify({"error": str(e)}), 500
# run
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=True)
