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

#  Initialization 
app = Flask(__name__)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///analysis_history.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
nltk.download('vader_lexicon', quiet=True)
from nltk.sentiment.vader import SentimentIntensityAnalyzer
analyzer = SentimentIntensityAnalyzer()

# Custom Word Scores
new_words = {
    'trash': -3.5, 'garbage': -3.5, 'unacceptable': -4.0, 'disaster': -4.0,
    'subpar': -3.0, 'brilliant': 3.5, 'perfect': 4.0, 'not bad': 1.5,
}
analyzer.lexicon.update(new_words)

# Database Models 
class AnalysisRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(100), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    results_summary = db.Column(db.Text, nullable=False)
    entries = db.relationship('FeedbackEntry', backref='run', lazy=True, cascade="all, delete-orphan")

class FeedbackEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('analysis_run.id'), nullable=False)
    text = db.Column(db.String(5000), nullable=False)
    sentiment = db.Column(db.String(20))
    confidence = db.Column(db.Float)
    emotion = db.Column(db.String(20))
    category = db.Column(db.String(20))
    urgency = db.Column(db.String(20))

# NLP Analysis Logic
def analyze_text(text):
    scores = analyzer.polarity_scores(text)
    sentiment = "Neutral"
    if scores['compound'] >= 0.05: sentiment = "Positive"
    elif scores['compound'] <= -0.05: sentiment = "Negative"
    confidence = scores['compound']
    text_lower = text.lower()
    emotion = "Neutral"
    if any(w in text_lower for w in ["angry", "hate", "furious", "unacceptable", "trash", "garbage"]): emotion = "Anger"
    elif any(w in text_lower for w in ["sad", "disappointed", "sorry", "disaster", "subpar"]): emotion = "Sadness"
    elif any(w in text_lower for w in ["love", "amazing", "joy", "fantastic", "brilliant", "perfect"]): emotion = "Joy"
    elif any(w in text_lower for w in ["surprise", "wow", "unexpected"]): emotion = "Surprise"
    elif any(w in text_lower for w in ["fear", "scared", "worried"]): emotion = "Fear"
    category = "General"
    if any(w in text_lower for w in ["product", "feature", "item", "pricing"]): category = "Product"
    if any(w in text_lower for w in ["service", "support", "agent"]): category = "Service"
    if any(w in text_lower for w in ["delivery", "shipping", "package"]): category = "Delivery"
    urgency = "Normal"
    if any(w in text_lower for w in ["urgent", "critical", "asap", "now"]): urgency = "Critical"
    elif any(w in text_lower for w in ["high priority", "soon"]): urgency = "High"
    return sentiment, confidence, emotion, category, urgency

# Flask Routes 
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        source_name = ""
        feedback_list = []
        is_dated_file = False
        
        text_feedback = request.form.get('text_feedback')
        if text_feedback and text_feedback.strip():
            source_name = "Text Input"
            feedback_list = [line for line in text_feedback.strip().split('\n') if line.strip()]

        elif 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            source_name = f"File: {file.filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            try:
                file.save(filepath)
                if filepath.endswith(('.csv', '.xls', '.xlsx')):
                    df = pd.read_csv(filepath) if filepath.endswith('.csv') else pd.read_excel(filepath)
                    feedback_col = next((col for col in df.columns if col.lower() == 'feedback'), df.columns[0])
                    if 'date' in [col.lower() for col in df.columns]:
                        is_dated_file = True
                        date_col = next(col for col in df.columns if col.lower() == 'date')
                        df[date_col] = pd.to_datetime(df[date_col]).dt.date
                        for date_val, group in df.groupby(date_col):
                            run_timestamp = datetime.combine(date_val, time())
                            new_run = AnalysisRun(source=f"{source_name} ({date_val})", timestamp=run_timestamp, results_summary="{}")
                            db.session.add(new_run)
                            db.session.flush()
                            for text in group[feedback_col].dropna().astype(str).tolist():
                                sentiment, confidence, emotion, category, urgency = analyze_text(text)
                                entry = FeedbackEntry(run_id=new_run.id, text=text, sentiment=sentiment, confidence=confidence, emotion=emotion, category=category, urgency=urgency)
                                db.session.add(entry)
                        db.session.commit()
                        return jsonify({"message": "Dated file processed successfully."})
                    else:
                        feedback_list = df[feedback_col].dropna().astype(str).tolist()
                elif filepath.endswith('.pdf'):
                    reader = PdfReader(filepath)
                    feedback_list = [line.strip() for line in "".join(p.extract_text() for p in reader.pages).split('\n') if line.strip()]
                else:
                    return jsonify({"error": "Unsupported file type"}), 400
            finally:
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            return jsonify({"error": "No feedback provided."}), 400

        if not feedback_list:
            return jsonify({"error": "No processable feedback found."}), 400

        # This part now runs for text input and non-dated files
        run_timestamp = datetime.utcnow()
        summary = { "sentiment": {"Positive": 0, "Negative": 0, "Neutral": 0}, "emotion": {}, "category": {}, "urgency": {} }
        new_run = AnalysisRun(source=source_name, timestamp=run_timestamp, results_summary="{}")
        db.session.add(new_run)
        db.session.flush()
        for text in feedback_list:
            sentiment, confidence, emotion, category, urgency = analyze_text(text)
            entry = FeedbackEntry(run_id=new_run.id, text=text, sentiment=sentiment, confidence=confidence, emotion=emotion, category=category, urgency=urgency)
            db.session.add(entry)
            if sentiment in summary["sentiment"]: summary["sentiment"][sentiment] += 1
            summary["emotion"][emotion] = summary["emotion"].get(emotion, 0) + 1
            summary["category"][category] = summary["category"].get(category, 0) + 1
            summary["urgency"][urgency] = summary["urgency"].get(urgency, 0) + 1
        pos_count, neg_count = summary['sentiment']['Positive'], summary['sentiment']['Negative']
        total_count = pos_count + neg_count
        summary['overall_score'] = ((pos_count - neg_count) / total_count * 100) if total_count > 0 else 0
        new_run.results_summary = json.dumps(summary)
        db.session.commit()
        return jsonify({"run_id": new_run.id, "source": new_run.source, "summary": summary})

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

# (The rest of the file is unchanged)
@app.route('/history_table', methods=['GET'])
def get_history_table():
    query = FeedbackEntry.query
    sentiment = request.args.get('sentiment')
    emotion = request.args.get('emotion')
    category = request.args.get('category')
    urgency = request.args.get('urgency')
    if sentiment: query = query.filter(FeedbackEntry.sentiment == sentiment)
    if emotion: query = query.filter(FeedbackEntry.emotion == emotion)
    if category: query = query.filter(FeedbackEntry.category == category)
    if urgency: query = query.filter(FeedbackEntry.urgency == urgency)
    entries = query.order_by(FeedbackEntry.id.desc()).all()
    return jsonify([{"id": e.id, "text": e.text, "sentiment": e.sentiment, "confidence": e.confidence, "emotion": e.emotion, "category": e.category, "urgency": e.urgency, "timestamp": e.run.timestamp.strftime('%Y-%m-%d %H:%M')} for e in entries])
@app.route('/history/summary')
def get_history_summary():
    try:
        all_entries = FeedbackEntry.query.all()
        summary = { "sentiment": {"Positive": 0, "Negative": 0, "Neutral": 0}, "emotion": {}, "category": {}, "urgency": {} }
        for entry in all_entries:
            if entry.sentiment and entry.sentiment in summary["sentiment"]: summary["sentiment"][entry.sentiment] += 1
            if entry.emotion: summary["emotion"][entry.emotion] = summary["emotion"].get(entry.emotion, 0) + 1
            if entry.category: summary["category"][entry.category] = summary["category"].get(entry.category, 0) + 1
            if entry.urgency: summary["urgency"][entry.urgency] = summary["urgency"].get(entry.urgency, 0) + 1
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": f"Could not generate history summary: {str(e)}"}), 500
@app.route('/history_entry/<int:id>', methods=['DELETE'])
def delete_entry(id):
    entry = FeedbackEntry.query.get(id)
    if entry:
        db.session.delete(entry)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"error": "Entry not found"}), 404
@app.route('/history/clear_all', methods=['DELETE'])
def clear_all_history():
    try:
        db.session.query(FeedbackEntry).delete()
        db.session.query(AnalysisRun).delete()
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
@app.route('/export/csv')
def export_csv():
    query = FeedbackEntry.query
    sentiment = request.args.get('sentiment')
    emotion = request.args.get('emotion')
    category = request.args.get('category')
    urgency = request.args.get('urgency')
    if sentiment: query = query.filter(FeedbackEntry.sentiment == sentiment)
    if emotion: query = query.filter(FeedbackEntry.emotion == emotion)
    if category: query = query.filter(FeedbackEntry.category == category)
    if urgency: query = query.filter(FeedbackEntry.urgency == urgency)
    entries = query.order_by(FeedbackEntry.id.desc()).all()
    mem_file = io.StringIO()
    writer = csv.writer(mem_file)
    writer.writerow(['ID', 'Timestamp', 'Feedback', 'Sentiment', 'Confidence', 'Emotion', 'Category', 'Urgency'])
    for entry in entries:
        timestamp = entry.run.timestamp.strftime('%Y-%m-%d %H:%M') if entry.run else 'N/A'
        writer.writerow([entry.id, timestamp, entry.text, entry.sentiment, f"{entry.confidence:.2f}", entry.emotion, entry.category, entry.urgency])
    mem_file.seek(0)
    return Response(mem_file, mimetype="text/csv", headers={"Content-disposition": "attachment; filename=filtered_sentiment_export.csv"})
@app.route('/download/csv/<int:run_id>')
def download_csv(run_id):
    run = AnalysisRun.query.get_or_404(run_id)
    entries = run.entries
    mem_file = io.StringIO()
    writer = csv.writer(mem_file)
    writer.writerow(['ID', 'Timestamp', 'Feedback', 'Sentiment', 'Confidence', 'Emotion', 'Category', 'Urgency'])
    for entry in entries:
        writer.writerow([entry.id, run.timestamp.strftime('%Y-%m-%d %H:%M'), entry.text, entry.sentiment, f"{entry.confidence:.2f}", entry.emotion, entry.category, entry.urgency])
    mem_file.seek(0)
    return Response(mem_file, mimetype="text/csv", headers={"Content-disposition": f"attachment; filename=analysis_run_{run_id}.csv"})
@app.route('/download/pdf/<int:run_id>')
def download_pdf(run_id):
    run = AnalysisRun.query.get_or_404(run_id)
    summary = json.loads(run.results_summary)
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    can.setFont("Helvetica-Bold", 16)
    can.drawString(72, 750, f"Sentiment Analysis Report - Run #{run_id}")
    can.setFont("Helvetica-Bold", 12)
    can.drawString(72, 720, "Summary")
    can.setFont("Helvetica", 10)
    score = summary.get('overall_score', 0)
    overall_sentiment = "Positive" if score > 0 else "Negative" if score < 0 else "Neutral"
    y = 700
    can.drawString(82, y, f"Overall Sentiment: {overall_sentiment} ({score:.1f}%)")
    y -= 15
    can.drawString(82, y, f"Source: {run.source}")
    y -= 25
    can.setFont("Helvetica-Bold", 10)
    can.drawString(82, y, "Sentiment Breakdown:")
    can.setFont("Helvetica", 10)
    for sentiment, count in summary.get('sentiment', {}).items():
        y -= 15
        can.drawString(92, y, f"- {sentiment}: {count}")
    can.save()
    packet.seek(0)
    return Response(packet, mimetype='application/pdf', headers={'Content-Disposition': f'attachment;filename=analysis_run_{run_id}.pdf'})
@app.route('/trends/sentiment')
def get_sentiment_trends():
    try:
        results = db.session.query(
            func.date(AnalysisRun.timestamp).label('date'),
            FeedbackEntry.sentiment,
            func.count(FeedbackEntry.id).label('count')
        ).join(AnalysisRun).group_by(func.date(AnalysisRun.timestamp), FeedbackEntry.sentiment).order_by(func.date(AnalysisRun.timestamp)).all()
        trends = defaultdict(lambda: {'Positive': 0, 'Negative': 0, 'Neutral': 0})
        for r in results:
            if r.date is None or r.sentiment is None: continue
            date_str = r.date if isinstance(r.date, str) else r.date.isoformat()
            trends[date_str][r.sentiment] = r.count
        sorted_dates = sorted(trends.keys())
        chart_data = {
            'labels': sorted_dates,
            'datasets': [
                {'label': 'Positive', 'data': [trends[date]['Positive'] for date in sorted_dates], 'borderColor': '#a8c8a4', 'tension': 0.1},
                {'label': 'Negative', 'data': [trends[date]['Negative'] for date in sorted_dates], 'borderColor': '#f5b7b1', 'tension': 0.1},
                {'label': 'Neutral', 'data': [trends[date]['Neutral'] for date in sorted_dates], 'borderColor': '#d5d8dc', 'tension': 0.1}
            ]
        }
        return jsonify(chart_data)
    except Exception as e:
        print(f"Error in /trends/sentiment: {e}")
        return jsonify({"error": f"Failed to generate trend data: {str(e)}"}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=8081)
