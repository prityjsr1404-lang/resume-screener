import os
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash, Response
from werkzeug.utils import secure_filename
import PyPDF2
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = "ai_resume_screener_pro"

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///screening_history.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Upload Configuration
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
ALLOWED_EXTENSIONS = {'pdf'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Database Model for History
class ScreeningResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_title = db.Column(db.String(200), nullable=False)
    candidate_name = db.Column(db.String(100), nullable=False)
    match_score = db.Column(db.Float, nullable=False)
    date_screened = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                if page.extract_text():
                    text += page.extract_text() + " "
    except Exception as e:
        print(f"Error: {e}")
    return text

def extract_key_skills(text):
    # AI ke bina basic skill extraction (aap isko aur advance kar sakte hain)
    common_skills = ["python", "java", "c++", "html", "css", "javascript", "flask", "sql", "react", "machine learning", "data analysis"]
    found_skills = [skill.upper() for skill in common_skills if skill in text.lower()]
    return ", ".join(found_skills) if found_skills else "Not Detected"

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        job_title = request.form.get('job_title', 'Untitled Role')
        job_description = request.form.get('job_description', '')
        
        if not job_description:
            flash("Please enter a Job Description.", "danger")
            return redirect(request.url)

        uploaded_files = request.files.getlist('resumes')
        if not uploaded_files or uploaded_files[0].filename == '':
            flash("Please upload resumes.", "danger")
            return redirect(request.url)

        results = []
        vectorizer = TfidfVectorizer(stop_words='english')
        
        try:
            jd_vector = vectorizer.fit_transform([job_description])
        except ValueError:
            flash("Job description is too short.", "danger")
            return redirect(request.url)

        for file in uploaded_files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                resume_text = extract_text_from_pdf(filepath)
                
                if resume_text.strip():
                    resume_vector = vectorizer.transform([resume_text])
                    similarity = cosine_similarity(jd_vector, resume_vector)[0][0]
                    score = round(similarity * 100, 2)
                    
                    # Extract Skills
                    skills = extract_key_skills(resume_text)
                    
                    # Save to Database
                    new_record = ScreeningResult(job_title=job_title, candidate_name=filename, match_score=score)
                    db.session.add(new_record)
                    
                    results.append({'filename': filename, 'score': score, 'skills': skills})
                
                os.remove(filepath)

        db.session.commit()
        results = sorted(results, key=lambda x: x['score'], reverse=True)
        
        return render_template('results.html', results=results, job_title=job_title)

    return render_template('index.html')

# Route to Export CSV
@app.route('/export')
def export_csv():
    records = ScreeningResult.query.all()
    data = [{"Job Role": r.job_title, "Candidate": r.candidate_name, "Score (%)": r.match_score, "Date": r.date_screened.strftime('%Y-%m-%d %H:%M')} for r in records]
    
    df = pd.DataFrame(data)
    csv_data = df.to_csv(index=False)
    
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=screening_history.csv"}
    )

# Route for History Dashboard
@app.route('/history')
def history():
    records = ScreeningResult.query.order_by(ScreeningResult.date_screened.desc()).all()
    return render_template('history.html', records=records)

if __name__ == '__main__':
    app.run(debug=True)